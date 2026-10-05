#!/usr/bin/env python3
"""GPUv1-E08 (debug variant): community inventory for the SNAP Facebook ego-network union.

Commands
--------
  cluster : build the undirected graph on the GPU, run chunked Louvain local
            moving (real CUDA compute, fixed seed) and write the deliverables.
  report  : reload ONLY the saved partition in a fresh process and recompute the
            community directory / cross-community edge list independently.
  doctor  : inspect the required input files and runtime dependencies without
            executing any training/inference.  Exit 78 if anything is missing.

The heavy graph work (graph residency on device, gain evaluation, community
aggregation, modularity, cross-edge masking) runs on CUDA.  The `cluster`
command hard-fails when CUDA is unavailable -- no CPU fallback, no mock data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

TASK_ID = "GPUv1-E08"
SCALE = "debug_only"
DEFAULT_SEED = 20240517
DEFAULT_CHUNK = 128
DEFAULT_MAX_SWEEPS = 60
MODULARITY_FLOOR = 0.25


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def sha256_file(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(block)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=False)
        fh.write("\n")


def safe_cudnn_version():
    """Never let a cuDNN query hard-fail the run: the graph math does not use
    cuDNN, so an LD_LIBRARY_PATH / bundled-version mismatch is only cosmetic
    metadata and must not abort an otherwise successful CUDA computation."""
    try:
        import torch
        v = torch.backends.cudnn.version()
        return list(v) if isinstance(v, (tuple, list)) else int(v)
    except Exception as exc:  # pragma: no cover - host specific
        return f"unavailable ({type(exc).__name__})"


# --------------------------------------------------------------------------- #
# input loading / validation
# --------------------------------------------------------------------------- #
def load_raw(input_dir):
    import numpy as np
    input_dir = Path(input_dir)
    edges = np.load(input_dir / "edges.npy")
    node_ids = np.load(input_dir / "node_ids.npy")
    return edges, node_ids


def prepare_graph(edges_raw, node_ids):
    """Validate + canonicalise the undirected simple graph."""
    import numpy as np

    info = {}
    edges = np.asarray(edges_raw)
    info["raw_edge_rows"] = int(edges.shape[0])
    if edges.ndim != 2 or edges.shape[1] != 2:
        raise ValueError(f"edges.npy must be (E,2); got {edges.shape}")
    if edges.size == 0:
        raise ValueError("edges.npy is empty")
    nids = np.asarray(node_ids).reshape(-1)
    n = int(nids.shape[0])
    if n <= 0:
        raise ValueError("node_ids.npy is empty")
    info["num_nodes"] = n

    edges = edges.astype(np.int64)
    lo, hi = int(edges.min()), int(edges.max())
    if lo < 0 or hi >= n:
        raise ValueError(f"edge endpoint out of range: [{lo}, {hi}] vs n={n}")

    self_loops = int((edges[:, 0] == edges[:, 1]).sum())
    if self_loops:
        edges = edges[edges[:, 0] != edges[:, 1]]
    info["self_loops_dropped"] = self_loops

    a = np.minimum(edges[:, 0], edges[:, 1])
    b = np.maximum(edges[:, 0], edges[:, 1])
    keys = a * n + b
    uniq, first = np.unique(keys, return_index=True)
    if uniq.size != edges.shape[0]:
        keep = np.sort(first)
        info["duplicate_edges_dropped"] = int(edges.shape[0] - uniq.size)
        edges = edges[keep]
    else:
        info["duplicate_edges_dropped"] = 0

    info["num_edges"] = int(edges.shape[0])
    info["edge_list_sha256"] = hashlib.sha256(
        np.ascontiguousarray(edges).tobytes()
    ).hexdigest()
    return np.ascontiguousarray(edges), n, info


# --------------------------------------------------------------------------- #
# GPU community detection: chunked Louvain local moving
# --------------------------------------------------------------------------- #
def torch_modularity(comm, u, v, deg, m, num_slots):
    import torch
    cu = comm.index_select(0, u)
    cv = comm.index_select(0, v)
    same = cu == cv
    internal = torch.bincount(cu[same], minlength=num_slots).to(torch.float64)
    tot_w = torch.bincount(comm, weights=deg, minlength=num_slots)
    return (internal / m - (tot_w / (2.0 * m)) ** 2).sum()


def gpu_cluster(edges, n, device, seed, chunk_size, max_sweeps, log=None):
    """Chunked (Jacobi/PLM style) Louvain local-moving on the GPU.

    For every chunk of nodes (random order, seeded) the exact gain
        dQ(i -> B) = (k_iB - k_iA)/m - k_i (tot_B - tot_A + k_i) / (2 m^2)
    is evaluated with dense CUDA scatter/gather kernels against the current
    community totals and the best strictly-positive move is applied.
    """
    import torch

    m = float(edges.shape[0])
    u = torch.as_tensor(edges[:, 0].copy(), dtype=torch.long, device=device)
    v = torch.as_tensor(edges[:, 1].copy(), dtype=torch.long, device=device)
    src = torch.cat((u, v))
    dst = torch.cat((v, u))
    num_arcs = int(src.numel())

    deg = torch.bincount(src, minlength=n).to(torch.float64)
    comm = torch.arange(n, dtype=torch.long, device=device)
    tot = deg.clone()

    gen = torch.Generator(device=device)
    gen.manual_seed(int(seed))
    ones = torch.ones(num_arcs, dtype=torch.float64, device=device)
    pos = torch.full((n,), -1, dtype=torch.long, device=device)
    idxbuf = torch.arange(chunk_size, dtype=torch.long, device=device)
    wbuf = torch.zeros(chunk_size * n, dtype=torch.float64, device=device)

    history = []
    best_comm = comm.clone()
    best_q = -float("inf")
    sweeps_done = 0

    for sweep in range(int(max_sweeps)):
        order = torch.randperm(n, generator=gen, device=device)
        moves = 0
        for start in range(0, n, chunk_size):
            cnodes = order[start:start + chunk_size]
            csz = int(cnodes.numel())

            pos.fill_(-1)
            pos.index_copy_(0, cnodes, idxbuf[:csz])
            s_pos = pos.index_select(0, src)
            mask = s_pos >= 0
            sel = s_pos[mask] * n + comm.index_select(0, dst[mask])

            wmat = wbuf[:csz * n]
            wmat.zero_()
            wmat.scatter_add_(0, sel, ones[:int(sel.numel())])
            wmat = wmat.view(csz, n)

            ci = comm.index_select(0, cnodes)
            k_to_own = wmat.gather(1, ci.view(-1, 1)).squeeze(1)
            tot_own = tot.index_select(0, cnodes)
            ki = deg.index_select(0, cnodes)

            delta = (wmat - k_to_own.view(-1, 1)) / m \
                - ki.view(-1, 1) * (tot.view(1, -1) - (tot_own - ki).view(-1, 1)) / (2.0 * m * m)
            delta.scatter_(1, ci.view(-1, 1), 0.0)          # no self-move
            best_val, best_c = delta.max(dim=1)
            take = best_val > 0.0

            newc = torch.where(take, best_c, ci)
            dtot = torch.where(take, ki, torch.zeros_like(ki))
            tot.index_add_(0, newc, dtot)
            tot.index_add_(0, ci, -dtot)
            comm.index_copy_(0, cnodes, newc)
            moves += int(take.sum().item())

        sweeps_done = sweep + 1
        q = float(torch_modularity(comm, u, v, deg, m, n).item())
        history.append({"sweep": sweeps_done, "moves": moves, "modularity": q})
        if log is not None:
            log(f"  sweep {sweeps_done:3d}: moves={moves:6d}  Q={q:.6f}")
        if q > best_q:
            best_q = q
            best_comm = comm.clone()
        if moves == 0:
            break

    comm = best_comm
    return {
        "comm": comm,
        "deg": deg,
        "u": u,
        "v": v,
        "history": history,
        "sweeps": sweeps_done,
        "modularity": best_q,
    }


def relabel_by_size(comm, n):
    """Deterministic relabelling: 0 = biggest community (ties by old id)."""
    import torch
    num_slots = int(comm.max().item()) + 1
    counts = torch.bincount(comm, minlength=num_slots)
    order = torch.argsort(counts, descending=True, stable=True)
    keep = order[counts[order] > 0]
    mapping = torch.full((num_slots,), -1, dtype=torch.long, device=comm.device)
    mapping[keep] = torch.arange(keep.numel(), dtype=torch.long, device=comm.device)
    return mapping[comm]


# --------------------------------------------------------------------------- #
# inventory (pure numpy, used by `report` as an independent recomputation)
# --------------------------------------------------------------------------- #
def numpy_inventory(comm, edges, n):
    import numpy as np

    comm = np.asarray(comm).reshape(-1)
    num_slots = int(comm.max()) + 1
    m = float(edges.shape[0])
    size = np.bincount(comm, minlength=num_slots).astype(np.int64)
    cu = comm[edges[:, 0]]
    cv = comm[edges[:, 1]]
    same = cu == cv
    internal = np.bincount(cu[same], minlength=num_slots).astype(np.int64)
    deg = np.bincount(np.concatenate((edges[:, 0], edges[:, 1])), minlength=n).astype(np.float64)
    tot_w = np.bincount(comm, weights=deg, minlength=num_slots)
    q = float(np.sum(internal.astype(np.float64) / m - (tot_w / (2.0 * m)) ** 2))
    cross = edges[~same].astype(np.int64)
    return size, internal, tot_w, q, cross


def build_summary(comm, edges, n, size, internal, tot_w, q, cross_count, meta=None):
    num_slots = int(size.shape[0])
    nonempty = [c for c in range(num_slots) if int(size[c]) > 0]
    communities = [
        {
            "community_id": int(c),
            "num_nodes": int(size[c]),
            "num_internal_edges": int(internal[c]),
            "degree_sum": float(tot_w[c]),
        }
        for c in nonempty
    ]
    summary = {
        "task_id": TASK_ID,
        "num_nodes": int(n),
        "num_edges": int(edges.shape[0]),
        "num_communities": int(len(nonempty)),
        "num_community_slots": int(num_slots),
        "modularity": float(q),
        "resolution": 1.0,
        "community_sizes": [int(size[c]) for c in nonempty],
        "internal_edge_counts": [int(internal[c]) for c in nonempty],
        "community_degree_sums": [float(tot_w[c]) for c in nonempty],
        "communities": communities,
        "total_internal_edges": int(internal[nonempty].sum()) if nonempty else 0,
        "total_cross_edges": int(cross_count),
        "largest_community_size": int(max([size[c] for c in nonempty])) if nonempty else 0,
        "smallest_community_size": int(min([size[c] for c in nonempty])) if nonempty else 0,
    }
    if meta:
        summary["meta"] = meta
    return summary


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def require_cuda():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for this task: torch.cuda.is_available() is False. "
            "No CPU fallback is provided by design."
        )
    return torch


def device_metadata():
    """Best-effort device metadata; every probe is individually guarded so a
    broken host-side library (e.g. an LD_LIBRARY_PATH cuDNN mismatch) cannot
    invalidate an otherwise successful CUDA graph computation."""
    import torch

    def probe(fn, default=None):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - host specific
            return f"unavailable ({type(exc).__name__})" if default is None else default

    meta = {
        "name": probe(lambda: torch.cuda.get_device_name(0), "unknown"),
        "count": probe(lambda: int(torch.cuda.device_count()), 0),
        "torch_version": probe(lambda: torch.__version__),
        "cuda_version": probe(lambda: torch.version.cuda),
        "cudnn_version": safe_cudnn_version(),
        "capability": probe(lambda: list(torch.cuda.get_device_capability(0)), []),
    }
    return meta


def cmd_cluster(args):
    import numpy as np

    timings = {}
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    torch = require_cuda()
    device = torch.device("cuda:0")
    timings["device_init_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    edges_raw, node_ids = load_raw(args.input)
    edges, n, ginfo = prepare_graph(edges_raw, node_ids)
    timings["load_and_validate_s"] = time.perf_counter() - t0
    print(f"[cluster] graph: n={n} m={ginfo['num_edges']} "
          f"(raw rows={ginfo['raw_edge_rows']}, dup dropped="
          f"{ginfo['duplicate_edges_dropped']})")

    torch.cuda.synchronize()
    t0 = time.perf_counter()
    result = gpu_cluster(
        edges, n, device,
        seed=args.seed,
        chunk_size=args.chunk_size,
        max_sweeps=args.max_sweeps,
        log=lambda s: print("[cluster]" + s),
    )
    torch.cuda.synchronize()
    timings["gpu_cluster_s"] = time.perf_counter() - t0

    comm_raw = result["comm"]
    q_raw = float(result["modularity"])

    torch.cuda.synchronize()
    t0 = time.perf_counter()
    comm = relabel_by_size(comm_raw, n)
    u, v, deg = result["u"], result["v"], result["deg"]
    m = float(edges.shape[0])
    num_slots = int(comm.max().item()) + 1
    size = torch.bincount(comm, minlength=num_slots)
    cu = comm.index_select(0, u)
    cv = comm.index_select(0, v)
    same = cu == cv
    internal = torch.bincount(cu[same], minlength=num_slots)
    tot_w = torch.bincount(comm, weights=deg, minlength=num_slots)
    q = float(torch_modularity(comm, u, v, deg, m, num_slots).item())
    cross_mask = (~same).cpu().numpy()
    torch.cuda.synchronize()
    timings["summary_gpu_s"] = time.perf_counter() - t0

    comm_np = comm.cpu().numpy().astype(np.int64)
    cross_edges = edges[cross_mask].astype(np.int64)
    size_np = size.cpu().numpy().astype(np.int64)
    internal_np = internal.cpu().numpy().astype(np.int64)
    tot_np = tot_w.cpu().numpy().astype(np.float64)

    t0 = time.perf_counter()
    summary = build_summary(
        comm_np, edges, n, size_np, internal_np, tot_np, q, cross_edges.shape[0],
        meta={"graph": ginfo, "seed": int(args.seed), "raw_modularity": q_raw},
    )
    np.save(out_dir / "communities.npy", comm_np)
    write_json(out_dir / "community_summary.json", summary)
    np.save(out_dir / "cross_edges.npy", cross_edges)

    state = {
        "comm": comm_np,
        "degrees": deg.cpu().numpy().astype(np.float64),
        "modularity_history": np.asarray([h["modularity"] for h in result["history"]], dtype=np.float64),
        "moves_history": np.asarray([h["moves"] for h in result["history"]], dtype=np.int64),
        "seed": np.asarray([int(args.seed)], dtype=np.int64),
        "chunk_size": np.asarray([int(args.chunk_size)], dtype=np.int64),
        "max_sweeps": np.asarray([int(args.max_sweeps)], dtype=np.int64),
        "sweeps_executed": np.asarray([int(result["sweeps"])], dtype=np.int64),
        "num_nodes": np.asarray([int(n)], dtype=np.int64),
        "num_edges": np.asarray([int(edges.shape[0])], dtype=np.int64),
        "modularity": np.asarray([float(q)], dtype=np.float64),
    }
    try:
        state["cpu_rng_state"] = torch.get_rng_state().numpy()
        state["cuda_rng_state"] = torch.cuda.get_rng_state().numpy()
    except Exception as exc:  # pragma: no cover - host specific
        state["rng_state_note"] = np.asarray([f"unavailable ({type(exc).__name__})"])
    np.savez(out_dir / "state.npz", **state)
    timings["save_s"] = time.perf_counter() - t0

    # ---- independent self-verification of the saved artefacts ---------------
    checks = {
        "all_nodes_assigned": bool(comm_np.shape[0] == n),
        "community_ids_non_negative": bool(comm_np.min() >= 0),
        "num_nonempty_communities_ge_2": bool(summary["num_communities"] >= 2),
        "not_all_singletons": bool(summary["num_communities"] < n),
        "not_single_community": bool(summary["num_communities"] > 1),
        "modularity_ge_floor": bool(q >= MODULARITY_FLOOR),
    }
    sizes_recheck, internal_recheck, tot_recheck, q_recheck, cross_recheck = numpy_inventory(
        np.load(out_dir / "communities.npy"), edges, n,
    )
    checks["numpy_modularity_matches"] = bool(abs(q_recheck - q) < 1e-9)
    checks["numpy_sizes_match"] = bool(np.array_equal(sizes_recheck, size_np))
    checks["numpy_internal_edges_match"] = bool(np.array_equal(internal_recheck, internal_np))
    checks["cross_edges_saved_match"] = bool(np.array_equal(cross_recheck, cross_edges))
    checks["internal_plus_cross_equals_m"] = bool(
        int(internal_np.sum()) + int(cross_edges.shape[0]) == int(edges.shape[0])
    )

    timings["total_wall_s"] = sum(v for k, v in timings.items() if k != "total_wall_s")
    try:
        mem_alloc = int(torch.cuda.max_memory_allocated())
        mem_resv = int(torch.cuda.max_memory_reserved())
    except Exception:  # pragma: no cover
        mem_alloc, mem_resv = -1, -1

    run = {
        "task_id": TASK_ID,
        "task_scale": SCALE,
        "status": "ok" if all(checks.values()) else "check_failed",
        "command": " ".join(sys.argv),
        "cwd": str(Path.cwd()),
        "seed": int(args.seed),
        "device": device_metadata(),
        "algorithm": {
            "name": "gpu_chunked_louvain_local_moving",
            "resolution": 1.0,
            "chunk_size": int(args.chunk_size),
            "max_sweeps": int(args.max_sweeps),
            "sweeps_executed": int(result["sweeps"]),
            "objective": "standard undirected modularity (each undirected edge counted once)",
        },
        "graph": ginfo,
        "timings_s": timings,
        "memory": {
            "cuda_peak_allocated_bytes": mem_alloc,
            "cuda_peak_reserved_bytes": mem_resv,
        },
        "results": {
            "num_communities": int(summary["num_communities"]),
            "modularity": float(q),
            "largest_community_size": int(summary["largest_community_size"]),
            "smallest_community_size": int(summary["smallest_community_size"]),
            "num_internal_edges": int(summary["total_internal_edges"]),
            "num_cross_edges": int(cross_edges.shape[0]),
        },
        "modularity_history": result["history"],
        "checks": checks,
        "inputs": {},
        "outputs": {},
    }

    for fname in ("edges.npy", "node_ids.npy"):
        p = Path(args.input) / fname
        if p.is_file():
            run["inputs"][fname] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    for fname in ("communities.npy", "community_summary.json", "cross_edges.npy", "state.npz"):
        p = out_dir / fname
        run["outputs"][fname] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}

    write_json(out_dir / "run.json", run)

    print(json.dumps({
        "status": run["status"],
        "num_communities": run["results"]["num_communities"],
        "modularity": run["results"]["modularity"],
        "cross_edges": run["results"]["num_cross_edges"],
        "sweeps": run["algorithm"]["sweeps_executed"],
        "total_wall_s": timings["total_wall_s"],
    }, indent=2))
    return 0 if run["status"] == "ok" else 1


def cmd_report(args):
    """Fresh-process recomputation of the directory from the saved partition."""
    import numpy as np

    t0 = time.perf_counter()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    edges_raw, node_ids = load_raw(args.input)
    edges, n, ginfo = prepare_graph(edges_raw, node_ids)

    comm = np.load(args.communities)
    comm = np.asarray(comm).reshape(-1)
    problems = []
    if comm.shape[0] != n:
        problems.append(f"partition has {comm.shape[0]} entries, expected {n}")
    if not np.issubdtype(comm.dtype, np.integer):
        problems.append(f"partition dtype is {comm.dtype}, expected integer")
    if comm.size and int(comm.min()) < 0:
        problems.append("negative community id")
    if problems:
        report = {"task_id": TASK_ID, "status": "invalid_partition", "problems": problems}
        write_json(out_dir / "report.json", report)
        print(json.dumps(report, indent=2))
        return 1

    comm = comm.astype(np.int64)
    size, internal, tot_w, q, cross = numpy_inventory(comm, edges, n)
    summary = build_summary(comm, edges, n, size, internal, tot_w, q, cross.shape[0],
                            meta={"graph": ginfo, "source_partition": str(args.communities)})
    np.save(out_dir / "cross_edges.npy", cross)
    write_json(out_dir / "community_summary.json", summary)

    nonempty = int((size > 0).sum())
    checks = {
        "all_nodes_assigned": True,
        "num_nonempty_communities_ge_2": bool(nonempty >= 2),
        "not_all_singletons": bool(nonempty < n),
        "not_single_community": bool(nonempty > 1),
        "modularity_ge_floor": bool(q >= MODULARITY_FLOOR),
        "internal_plus_cross_equals_m": bool(int(internal.sum()) + int(cross.shape[0]) == int(edges.shape[0])),
    }
    report = {
        "task_id": TASK_ID,
        "status": "ok" if all(checks.values()) else "check_failed",
        "command": " ".join(sys.argv),
        "partition_file": str(args.communities),
        "num_nodes": int(n),
        "num_edges": int(edges.shape[0]),
        "num_communities": int(nonempty),
        "modularity": float(q),
        "num_internal_edges": int(internal.sum()),
        "num_cross_edges": int(cross.shape[0]),
        "community_sizes": [int(x) for x in size[size > 0]],
        "internal_edge_counts": [int(x) for x in internal[size > 0]],
        "checks": checks,
        "wall_s": time.perf_counter() - t0,
    }
    write_json(out_dir / "report.json", report)
    print(json.dumps({k: report[k] for k in ("status", "num_communities", "modularity",
                                             "num_cross_edges", "checks")}, indent=2))
    return 0 if report["status"] == "ok" else 1


def cmd_doctor(args):
    """Inspect required files/dependencies only -- never runs the algorithm."""
    import numpy as np

    report = {"task_id": TASK_ID, "command": "doctor", "checks": [], "missing": []}

    def add(name, ok, detail=""):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": str(detail)})
        if not ok:
            report["missing"].append({"item": name, "detail": str(detail)})

    input_dir = Path(args.input)
    add("input_dir_exists", input_dir.is_dir(), str(input_dir))

    manifest = None
    mpath = input_dir / "manifest.json"
    if mpath.is_file():
        try:
            manifest = json.loads(mpath.read_text())
            add("manifest_parse", True, str(mpath))
        except Exception as exc:  # pragma: no cover
            add("manifest_parse", False, repr(exc))
    else:
        add("manifest_json_present", False, str(mpath))

    for fname in ("edges.npy", "node_ids.npy"):
        p = input_dir / fname
        exists = p.is_file()
        add(f"file:{fname}", exists, str(p))
        if exists and manifest and isinstance(manifest.get("files"), dict) \
                and fname in manifest["files"]:
            digest = sha256_file(p)
            add(f"sha256:{fname}", digest == manifest["files"][fname], digest)

    try:
        if (input_dir / "edges.npy").is_file():
            e = np.load(input_dir / "edges.npy", mmap_mode="r")
            add("edges_shape_E2", e.ndim == 2 and e.shape[1] == 2, str(e.shape))
            add("edges_dtype_integer", np.issubdtype(e.dtype, np.integer), str(e.dtype))
            if manifest and "edges" in manifest:
                add("edges_count_matches_manifest", int(e.shape[0]) == int(manifest["edges"]),
                    f"actual={int(e.shape[0])} manifest={manifest['edges']}")
        if (input_dir / "node_ids.npy").is_file():
            nid = np.load(input_dir / "node_ids.npy", mmap_mode="r")
            add("node_ids_1d", nid.ndim == 1, str(nid.shape))
            if manifest and "nodes" in manifest:
                add("nodes_count_matches_manifest", int(nid.shape[0]) == int(manifest["nodes"]),
                    f"actual={int(nid.shape[0])} manifest={manifest['nodes']}")
    except Exception as exc:
        add("numpy_inspection", False, repr(exc))

    try:
        import torch
        add("torch_import", True, torch.__version__)
        cuda_ok = bool(torch.cuda.is_available())
        add("cuda_available", cuda_ok, "torch.cuda.is_available()")
        if cuda_ok:
            add("cuda_device0", True, torch.cuda.get_device_name(0))
    except Exception as exc:
        add("torch_import", False, repr(exc))
        add("cuda_available", False, "torch unavailable")

    report["available"] = len(report["missing"]) == 0
    print(json.dumps(report, indent=2))
    return 0 if report["available"] else 78


# --------------------------------------------------------------------------- #
def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=f"{TASK_ID}: GPU community inventory for the SNAP Facebook ego-union graph.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cluster", help="run GPU community detection and write the deliverables")
    p.add_argument("--input", required=True, help="input directory (edges.npy, node_ids.npy)")
    p.add_argument("--output", required=True, help="output directory")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="fixed RNG seed")
    p.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK, help="nodes per parallel move step")
    p.add_argument("--max-sweeps", type=int, default=DEFAULT_MAX_SWEEPS, help="maximum local-moving sweeps")
    p.set_defaults(func=cmd_cluster)

    r = sub.add_parser("report", help="recompute the directory from a saved partition (fresh process)")
    r.add_argument("--input", required=True, help="input directory")
    r.add_argument("--communities", required=True, help="path to communities.npy")
    r.add_argument("--output", required=True, help="output directory for the recomputed report")
    r.set_defaults(func=cmd_report)

    d = sub.add_parser("doctor", help="inspect inputs/dependencies without executing the workload")
    d.add_argument("--input", required=True, help="input directory")
    d.set_defaults(func=cmd_doctor)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except RuntimeError as exc:
        print(json.dumps({"task_id": TASK_ID, "status": "error", "error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
