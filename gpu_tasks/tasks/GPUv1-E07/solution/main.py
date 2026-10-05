#!/usr/bin/env python3
"""GPUv1-E07 - PageRank on the SNAP Twitter ego-network union (CUDA).

Graph:    input/edges.npy   (E, 2) int64 dense source/target indices
          input/node_ids.npy (N,)  int64 original Twitter ids (row order == rank order)

Model:    r = alpha * (A_hat^T r) + alpha * (dangling_sum / N) + (1 - alpha) / N
          * every input row is one directed edge (parallel edges are counted with
            their multiplicity, exactly as the raw SNAP file stores them);
          * out-degree normalisation per source row;
          * uniform teleport and uniform dangling-mass redistribution;
          * uniform start vector 1/N;
          * stop when the L1 change between two consecutive iterates is < 1e-7
            or after at most 1000 iterations (alpha = 0.85).

All edge contribution propagation and all reductions of the main iteration are
executed on the GPU with PyTorch float64 CUDA kernels.  The CPU is only used to
load the arrays, to hash the graph, and to serialise the deliverables.  An
independent SciPy oracle is run afterwards purely as a self-check (it never
produces the delivered ranks).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time

import numpy as np

try:  # torch is required; imported lazily-friendly at module level
    import torch
except Exception as exc:  # pragma: no cover
    torch = None
    _TORCH_ERR = exc

ALPHA_DEFAULT = 0.85
TOL_DEFAULT = 1e-7
MAX_ITER_DEFAULT = 1000


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _sha256_bytes(*chunks: bytes) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
    return h.hexdigest()


def graph_hash(node_ids: np.ndarray, edges: np.ndarray) -> str:
    """Canonical, order independent hash of (node ids, edge multiset)."""
    ids = np.ascontiguousarray(node_ids, dtype="<i8")
    e = np.asarray(edges)
    if e.size:
        order = np.lexsort((np.ascontiguousarray(e[:, 1], dtype="<i8"),
                            np.ascontiguousarray(e[:, 0], dtype="<i8")))
        e_sorted = np.ascontiguousarray(e[order], dtype="<i8")
    else:
        e_sorted = np.zeros((0, 2), dtype="<i8")
    return _sha256_bytes(
        b"GPUv1-E07/pagerank/graph:v1|",
        ids.tobytes(),
        np.array(ids.shape, dtype="<i8").tobytes(),
        e_sorted.tobytes(),
        np.array(e_sorted.shape, dtype="<i8").tobytes(),
    )


def load_inputs(input_dir: str):
    edges_path = os.path.join(input_dir, "edges.npy")
    ids_path = os.path.join(input_dir, "node_ids.npy")
    if not os.path.isfile(edges_path):
        raise FileNotFoundError("missing %s" % edges_path)
    if not os.path.isfile(ids_path):
        raise FileNotFoundError("missing %s" % ids_path)
    edges = np.load(edges_path)
    node_ids = np.load(ids_path)
    if edges.ndim != 2 or edges.shape[1] != 2:
        raise ValueError("edges.npy must have shape (E, 2), got %r" % (edges.shape,))
    if node_ids.ndim != 1:
        raise ValueError("node_ids.npy must be 1-D, got %r" % (node_ids.shape,))
    edges = np.ascontiguousarray(edges, dtype=np.int64)
    node_ids = np.ascontiguousarray(node_ids, dtype=np.int64)
    n = int(node_ids.shape[0])
    if edges.size:
        lo, hi = int(edges.min()), int(edges.max())
        if lo < 0 or hi >= n:
            raise ValueError("edge indices out of range [0, %d): min=%d max=%d" % (n, lo, hi))
    return edges, node_ids


def pick_device(requested: str = "auto") -> "torch.device":
    if torch is None:  # pragma: no cover
        raise RuntimeError("PyTorch is required: %s" % _TORCH_ERR)
    if requested in ("auto", "cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA device is required but torch.cuda.is_available() is False")
        return torch.device("cuda")
    return torch.device(requested)


# --------------------------------------------------------------------------- #
# GPU PageRank core
# --------------------------------------------------------------------------- #
class GpuPageRank:
    """Compact GPU description of the graph + the iteration operator T."""

    def __init__(self, edges: np.ndarray, n: int, device: "torch.device", sort_by_target: bool = True):
        self.n = int(n)
        self.device = device
        e = np.ascontiguousarray(edges, dtype=np.int64)
        src = torch.from_numpy(e[:, 0]).to(device=device, dtype=torch.int64)
        dst = torch.from_numpy(e[:, 1]).to(device=device, dtype=torch.int64)
        if sort_by_target and dst.numel() > 0:
            # group sources that write into the same target -> better coalescing
            order = torch.argsort(dst, stable=True)
            src = src[order]
            dst = dst[order]
        self.src = src
        self.dst = dst
        self.m = int(dst.numel())
        # out-degree (counts parallel edges), computed on the GPU
        deg = torch.bincount(self.src, minlength=self.n).to(torch.float64)
        self.deg = deg
        self.dangling_mask = deg == 0
        self.n_dangling = int(self.dangling_mask.sum().item())
        self.inv_deg = torch.where(deg > 0, 1.0 / torch.clamp(deg, min=1.0),
                                   torch.zeros_like(deg))

    def step(self, r: "torch.Tensor", alpha: float) -> "torch.Tensor":
        """Return T(r): r_new = alpha * P^T r + alpha * dangling/N + (1-alpha)/N."""
        if self.n_dangling:
            dangling_sum = r[self.dangling_mask].sum()
        else:
            dangling_sum = torch.zeros((), dtype=r.dtype, device=r.device)
        vals = r[self.src] * self.inv_deg[self.src]   # per-edge scaled mass (GPU gather)
        contrib = torch.zeros(self.n, dtype=r.dtype, device=r.device)
        contrib.index_add_(0, self.dst, vals)         # edge contribution (GPU scatter-add)
        teleport = (alpha * dangling_sum + (1.0 - alpha)) / self.n
        return alpha * contrib + teleport

    def l1_residual(self, r: "torch.Tensor", alpha: float) -> float:
        """||T(r) - r||_1 evaluated on the GPU."""
        return float((self.step(r, alpha) - r).abs().sum().item())


def run_pagerank(engine: GpuPageRank, r0: "torch.Tensor", alpha: float, tol: float,
                 max_iter: int, start_iter: int):
    r = r0
    iters = int(start_iter)
    diff = float("inf")
    converged = False
    t0 = time.time()
    while iters < max_iter:
        r_new = engine.step(r, alpha)
        diff = float((r_new - r).abs().sum().item())   # GPU reduction
        r = r_new
        iters += 1
        if diff < tol:
            converged = True
            break
    if iters == int(start_iter):  # nothing left to do (already at max_iter)
        diff = engine.l1_residual(r, alpha)
    elapsed = time.time() - t0
    return r, iters, diff, converged, elapsed


# --------------------------------------------------------------------------- #
# independent CPU oracle (self-check only, never used for delivered ranks)
# --------------------------------------------------------------------------- #
def scipy_oracle_check(edges: np.ndarray, n: int, ranks: np.ndarray, alpha: float):
    out = {"available": False}
    try:
        import scipy.sparse as sp
    except Exception as exc:  # pragma: no cover
        out["error"] = "scipy unavailable: %s" % exc
        return out
    src = edges[:, 0]
    dst = edges[:, 1]
    A = sp.csr_matrix((np.ones(edges.shape[0], dtype=np.float64), (src, dst)), shape=(n, n))
    deg = np.asarray(A.sum(axis=1)).ravel()
    dangling = deg == 0
    inv = np.where(deg > 0, 1.0 / np.where(deg > 0, deg, 1.0), 0.0)
    r = np.asarray(ranks, dtype=np.float64)
    dsum = float(r[dangling].sum()) if dangling.any() else 0.0
    r_new = alpha * (A.T @ (r * inv)) + (alpha * dsum + (1.0 - alpha)) / n
    out.update({
        "available": True,
        "sum": float(r.sum()),
        "min": float(r.min()),
        "nonnegative": bool((r >= 0).all()),
        "fixed_point_l1": float(np.abs(r_new - r).sum()),
        "fixed_point_step_l1": float(np.abs((alpha * (A.T @ (r_new * inv)) + (alpha * float(r_new[dangling].sum()) + (1.0 - alpha)) / n) - r_new).sum()),
        "graph": "0.85 uniform teleport, uniform dangling redistribution, parallel edges counted",
    })
    return out


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_rank(args) -> int:
    t_start = time.time()
    input_dir = args.input
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    alpha = float(args.alpha)
    tol = float(args.tol)
    max_iter = int(args.max_iter)

    edges, node_ids = load_inputs(input_dir)
    n = int(node_ids.shape[0])
    ghash = graph_hash(node_ids, edges)

    device = pick_device(args.device)
    torch.manual_seed(0)

    resumed_from = None
    start_iter = 0
    converged_before = False
    prev_diff = None
    if args.resume:
        st_path = args.resume
        if not os.path.isfile(st_path):
            raise FileNotFoundError("resume state not found: %s" % st_path)
        st = np.load(st_path, allow_pickle=False)
        st_hash = str(st["graph_hash"].item()) if st["graph_hash"].ndim == 0 else str(st["graph_hash"][0])
        st_n = int(st["n"]) if "n" in st.files else int(np.asarray(st["ranks"]).shape[0])
        st_alpha = float(st["alpha"])
        if st_hash != ghash:
            raise ValueError(
                "resume state graph hash mismatch: state=%s input=%s (refusing to continue on a different graph)"
                % (st_hash, ghash))
        if st_n != n:
            raise ValueError("resume state node count %d != input node count %d" % (st_n, n))
        if abs(st_alpha - alpha) > 1e-15:
            raise ValueError("resume state alpha %r != requested alpha %r" % (st_alpha, alpha))
        r_np = np.asarray(st["ranks"], dtype=np.float64).copy()
        if r_np.shape != (n,):
            raise ValueError("resume ranks shape %r != (%d,)" % (r_np.shape, n))
        start_iter = int(st["iteration"])
        converged_before = bool(st["converged"]) if "converged" in st.files else False
        prev_diff = float(st["last_l1_diff"]) if "last_l1_diff" in st.files else None
        resumed_from = os.path.abspath(st_path)

    engine = GpuPageRank(edges, n, device, sort_by_target=not args.no_sort)

    if resumed_from is None:
        r = torch.full((n,), 1.0 / n, dtype=torch.float64, device=device)
        # exact uniform start: rescale so the vector sums to 1 in float64
        r = r / r.sum()
    else:
        r = torch.from_numpy(r_np).to(device=device, dtype=torch.float64)

    r, iters, diff, converged, elapsed = run_pagerank(
        engine, r, alpha, tol, max_iter, start_iter)

    ranks = r.detach().to("cpu").numpy().astype(np.float64)

    # internal GPU fixed point residual of the returned vector
    gpu_residual = engine.l1_residual(r, alpha)

    # ---------------- deliverables ----------------
    ranks_path = os.path.join(output_dir, "ranks.npy")
    np.save(ranks_path, ranks)

    state_path = os.path.join(output_dir, "state.npz")
    np.savez(
        state_path,
        ranks=ranks,
        iteration=np.int64(iters),
        alpha=np.float64(alpha),
        graph_hash=np.array(ghash),
        n=np.int64(n),
        tol=np.float64(tol),
        max_iter=np.int64(max_iter),
        converged=np.bool_(converged),
        last_l1_diff=np.float64(diff),
        model=np.array("0.85-uniform-teleport;uniform-dangling;parallel-edges-counted"),
    )

    # top 100: rank descending, ties broken by original node id ascending
    order = np.lexsort((node_ids, -ranks))
    top_idx = order[:100]
    top_nodes = [
        {
            "rank_position": int(i + 1),
            "node_id": int(node_ids[j]),
            "dense_index": int(j),
            "rank": float(ranks[j]),
        }
        for i, j in enumerate(top_idx)
    ]
    top_payload = {
        "format": "top_nodes_v1",
        "description": "top 100 nodes by PageRank descending; ties broken by original node_id ascending",
        "tie_break": "rank desc, original node_id asc",
        "alpha": alpha,
        "count": int(len(top_nodes)),
        "top_nodes": top_nodes,
        "top_node_ids": [int(t["node_id"]) for t in top_nodes],
    }
    with open(os.path.join(output_dir, "top_nodes.json"), "w") as fh:
        json.dump(top_payload, fh, indent=2)

    oracle = scipy_oracle_check(edges, n, ranks, alpha)

    dev_name = torch.cuda.get_device_name(device) if device.type == "cuda" else platform.processor()
    run_info = {
        "task": "GPUv1-E07",
        "command": "rank",
        "mode": "resume" if resumed_from else "fresh",
        "resumed_from": resumed_from,
        "input": os.path.abspath(input_dir),
        "output": os.path.abspath(output_dir),
        "nodes": n,
        "edge_rows": int(edges.shape[0]),
        "unique_directed_edges": None,
        "graph_hash": ghash,
        "alpha": alpha,
        "teleport": "uniform",
        "dangling": "uniform redistribution",
        "edge_multiplicity": "every input row is one edge (parallel edges counted)",
        "tol": tol,
        "max_iter": max_iter,
        "start_vector": "uniform 1/N",
        "device": str(device),
        "device_name": dev_name,
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "dtype": "float64",
        "iterations_total": iters,
        "iterations_this_run": iters - start_iter,
        "converged": converged,
        "last_l1_diff": diff,
        "previous_l1_diff": prev_diff,
        "converged_before_resume": converged_before,
        "gpu_fixed_point_l1_residual": gpu_residual,
        "elapsed_sec": elapsed,
        "total_sec": time.time() - t_start,
        "ranks_sum": float(ranks.sum()),
        "ranks_min": float(ranks.min()),
        "n_dangling": engine.n_dangling,
        "oracle_check": oracle,
        "artifacts": ["ranks.npy", "top_nodes.json", "state.npz", "run.json"],
    }
    with open(os.path.join(output_dir, "run.json"), "w") as fh:
        json.dump(run_info, fh, indent=2)

    print("[rank] n=%d edges=%d device=%s" % (n, edges.shape[0], dev_name))
    print("[rank] iterations_total=%d this_run=%d converged=%s last_l1_diff=%.3e"
          % (iters, iters - start_iter, converged, diff))
    print("[rank] gpu fixed-point L1 residual=%.3e  ranks_sum=%.15f"
          % (gpu_residual, float(ranks.sum())))
    if oracle.get("available"):
        print("[rank] oracle: sum=%.15f min=%.3e fixed_point_l1=%.3e nonneg=%s"
              % (oracle["sum"], oracle["min"], oracle["fixed_point_l1"], oracle["nonnegative"]))
    print("[rank] wrote %s" % ", ".join(run_info["artifacts"]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="GPU PageRank (GPUv1-E07)")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("rank", help="compute PageRank on the input graph with CUDA")
    r.add_argument("--input", default="input", help="input directory (edges.npy, node_ids.npy)")
    r.add_argument("--output", default="output", help="output directory")
    r.add_argument("--resume", default=None,
                   help="path to a state.npz produced by a previous run on the same graph")
    r.add_argument("--alpha", type=float, default=ALPHA_DEFAULT)
    r.add_argument("--tol", type=float, default=TOL_DEFAULT, help="L1 stop tolerance")
    r.add_argument("--max-iter", type=int, default=MAX_ITER_DEFAULT)
    r.add_argument("--device", default="auto", help="auto|cuda|cpu")
    r.add_argument("--no-sort", action="store_true", help="skip GPU-side edge reordering")
    r.set_defaults(func=cmd_rank)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
