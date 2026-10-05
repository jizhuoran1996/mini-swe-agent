#!/usr/bin/env python
"""GPUv1-E06: reusable content partition of 1M real SIFT descriptors on CUDA.

Usage
-----
    python solution/main.py fit    --input input --output output
    python solution/main.py assign --centroids output/centroids.npy \
                                   --vectors input/vectors.npy \
                                   --output output/reassigned.npy

`fit` runs seeded k-means (K=32) with all distance/assignment/reduction work
executed as CUDA kernels by PyTorch, writes
    output/centroids.npy   (K, D) float32
    output/assignments.npy (N,)   int32
    output/counts.npy      (K,)   int64
    output/run.json
and never forms an N x N distance matrix.

`assign` loads pre-trained centroids in a fresh process and assigns vectors
without any re-training.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch  # noqa: E402

from kmeans_cuda import (  # noqa: E402
    DEFAULT_CHUNK,
    assign_and_sse,
    assign_chunked,
    fit_kmeans,
    get_device,
    load_vectors,
    sync,
)

K_DEFAULT = 32
SEED_DEFAULT = 0
MAX_ITER_DEFAULT = 20
TOL_DEFAULT = 1e-6
SUBSAMPLE_DEFAULT = 65536
INIT_SUBSAMPLE_DEFAULT = 262144
INIT_ITERS_DEFAULT = 20


def _cuda_info(device: torch.device):
    props = torch.cuda.get_device_properties(device)
    return {
        "device": str(device),
        "gpu_name": props.name,
        "gpu_total_memory_gib": props.total_memory / 2**30,
        "cuda_capability": f"{props.major}.{props.minor}",
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "python": platform.python_version(),
        "numpy": np.__version__,
    }


def cmd_fit(args) -> int:
    os.makedirs(args.output, exist_ok=True)
    vectors_path = os.path.join(args.input, "vectors.npy")
    if not os.path.isfile(vectors_path):
        raise FileNotFoundError(vectors_path)

    device = get_device()
    t_load = time.perf_counter()
    sync(device)
    x = load_vectors(vectors_path, device)
    sync(device)
    t_load = time.perf_counter() - t_load
    n, d = x.shape
    k = args.k
    if k <= 0 or k > n:
        raise ValueError(f"invalid K={k} for {n} vectors")

    print(
        f"[fit] loaded {vectors_path}: n={n} d={d} dtype={x.dtype} "
        f"device={x.device} in {t_load:.2f}s"
    )

    res = fit_kmeans(
        x,
        k=k,
        seed=args.seed,
        max_iter=args.max_iter,
        chunk=args.chunk,
        tol=args.tol,
        subsample=args.subsample,
        init_subsample=args.init_subsample,
        init_iters=args.init_iters,
    )

    centroids = res["centroids"]
    assignments = res["assignments"]
    counts = res["counts"]

    # ------------------------- self verification (all on GPU) --------------
    coverage = int(assignments.numel())
    in_range = bool(((assignments >= 0) & (assignments < k)).all().item())
    counts_match = bool(torch.equal(counts, torch.bincount(assignments, minlength=k)))
    # independent recomputation of SSE from the written artifacts
    _, sse_check = assign_and_sse(x, centroids, chunk=args.chunk, want_sse=True)
    # independent nearest-centroid check with a different (matmul) formulation
    xi2 = (x * x).sum(dim=1, keepdim=True)
    c2 = (centroids * centroids).sum(dim=1).unsqueeze(0)
    match_total = 0
    with torch.no_grad():
        for s in range(0, n, args.chunk):
            e = min(s + args.chunk, n)
            dmat = xi2[s:e] - 2.0 * (x[s:e] @ centroids.t()) + c2
            a2 = torch.argmin(dmat, dim=1)
            match_total += int((a2 == assignments[s:e]).sum().item())
    nearest_match = match_total / n

    sse_val = float(sse_check.item())
    baseline = res["baseline_sse"]
    reduction = 1.0 - sse_val / baseline if baseline > 0 else 0.0

    centroids_np = centroids.detach().cpu().numpy().astype(np.float32)
    assignments_np = assignments.detach().cpu().numpy().astype(np.int32)
    counts_np = counts.detach().cpu().numpy().astype(np.int64)

    np.save(os.path.join(args.output, "centroids.npy"), centroids_np)
    np.save(os.path.join(args.output, "assignments.npy"), assignments_np)
    np.save(os.path.join(args.output, "counts.npy"), counts_np)

    run = {
        "task": "GPUv1-E06",
        "scale": "debug_only",
        "reference_large": False,
        "command": " ".join(sys.argv),
        "seed": int(args.seed),
        "config": {
            "k": int(k),
            "dim": int(d),
            "n_vectors": int(n),
            "max_iter": int(args.max_iter),
            "tol": float(args.tol),
            "distance_chunk_rows": int(args.chunk),
            "init": (
                "seeded k-means++ on a random "
                f"{int(min(args.init_subsample, n))}-vector subsample, refined "
                f"with {int(args.init_iters)} Lloyd iterations on that subsample"
            ),
            "init_subsample": int(min(args.init_subsample, n)),
            "init_refine_iters": int(args.init_iters),
            "lloyd_iterations_on_full_data": int(res["n_iter"]),
            "dtype": "float32",
            "device": "cuda",
        },
        "algorithm": {
            "type": "lloyd k-means (full data, no prefix, no resampling)",
            "distance": "batched squared Euclidean ||x-c||^2, chunked",
            "assignment": "CUDA argmin reduction over K",
            "reduction": "CUDA index_add_ scatter-reduce for centroid sums, "
                         "bincount for counts, float64 accumulators for SSE",
            "full_nxn_distance_matrix": False,
            "min_lloyd_updates": 1,
            "cuda_kernels": [
                "batched squared-Euclidean distance: elementwise sub/mul + "
                "torch.sum row reduction (CUDA) over (chunk, K, D) tiles",
                "assignment: torch.argmin reduction over K (CUDA)",
                "centroid sums: torch.Tensor.index_add_ scatter-reduce (CUDA)",
                "counts: torch.bincount reduction (CUDA)",
                "SSE/objective: torch.sum reductions accumulated in float64 (CUDA)",
            ],
            "empty_cluster_policy": (
                "re-seed empty clusters with the farthest points from their "
                "assigned centroid (deterministic, recorded per iteration)"
            ),
        },
        "cuda": _cuda_info(device),
        "timing": {
            "synchronized_before_timing": True,
            "load_s": t_load,
            **res["timing"],
        },
        "init_details": res.get("init", {}),
        "iterations": res["history"],
        "sse_history": [h["sse"] for h in res["history"]],
        "empty_cluster_events": res["empty_events"],
        "converged": bool(res["converged"]),
        "n_iterations": int(res["n_iter"]),
        "final_sse": sse_val,
        "baseline_single_mean_sse": baseline,
        "sse_reduction_vs_single_mean": reduction,
        "coverage": {
            "n_vectors": int(n),
            "assigned": coverage,
            "unassigned": int(n - coverage),
            "all_indices_in_range": in_range,
            "counts_sum": int(counts_np.sum()),
            "counts_match_assignments": counts_match,
            "min_cluster_size": int(counts_np.min()),
            "max_cluster_size": int(counts_np.max()),
        },
        "centroid_is_cluster_mean": {
            "max_abs_residual": res["mean_residual"]["max_abs"],
            "max_rel_residual": res["mean_residual"]["max_rel"],
            "mean_rel_residual": res["mean_residual"]["mean_rel"],
        },
        "self_check": {
            "nearest_centroid_match_fraction": nearest_match,
            "sse_recomputed": sse_val,
        },
        "artifacts": {
            "centroids.npy": {"shape": list(centroids_np.shape), "dtype": "float32"},
            "assignments.npy": {"shape": list(assignments_np.shape), "dtype": "int32"},
            "counts.npy": {"shape": list(counts_np.shape), "dtype": "int64"},
        },
    }
    with open(os.path.join(args.output, "run.json"), "w") as f:
        json.dump(run, f, indent=2)

    print(
        f"[fit] done: iters={res['n_iter']} converged={res['converged']} "
        f"final_sse={sse_val:.3f} baseline={baseline:.3f} "
        f"reduction={reduction*100:.2f}% coverage={coverage}/{n} "
        f"nearest_match={nearest_match:.6f} max_rel_mean_residual="
        f"{res['mean_residual']['max_rel']:.3e} total={res['timing']['total_fit_s']:.2f}s"
    )
    return 0


def cmd_assign(args) -> int:
    device = get_device()
    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.perf_counter()
    sync(device)
    x = load_vectors(args.vectors, device)
    cent_np = np.load(args.centroids).astype(np.float32)
    if cent_np.ndim != 2 or cent_np.shape[1] != x.shape[1]:
        raise ValueError(
            f"centroid shape {cent_np.shape} incompatible with vectors {tuple(x.shape)}"
        )
    centroids = torch.from_numpy(np.ascontiguousarray(cent_np)).to(device)
    assign = assign_chunked(x, centroids, chunk=args.chunk)
    sync(device)
    dt = time.perf_counter() - t0

    assign_np = assign.detach().cpu().numpy().astype(np.int32)
    np.save(args.output, assign_np)
    print(
        f"[assign] {x.shape[0]} vectors -> {cent_np.shape[0]} clusters "
        f"in {dt:.2f}s (device={device}); wrote {args.output}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-E06 CUDA k-means content partition (SIFT1M, K=32)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fit", help="train k-means on input/vectors.npy and write artifacts")
    f.add_argument("--input", required=True, help="directory containing vectors.npy")
    f.add_argument("--output", required=True, help="output directory")
    f.add_argument("--k", type=int, default=K_DEFAULT)
    f.add_argument("--seed", type=int, default=SEED_DEFAULT)
    f.add_argument("--max-iter", type=int, default=MAX_ITER_DEFAULT)
    f.add_argument("--tol", type=float, default=TOL_DEFAULT)
    f.add_argument("--chunk", type=int, default=DEFAULT_CHUNK)
    f.add_argument("--subsample", type=int, default=SUBSAMPLE_DEFAULT)
    f.add_argument("--init-subsample", type=int, default=INIT_SUBSAMPLE_DEFAULT)
    f.add_argument("--init-iters", type=int, default=INIT_ITERS_DEFAULT)
    f.set_defaults(func=cmd_fit)

    a = sub.add_parser("assign", help="assign vectors with pre-trained centroids")
    a.add_argument("--centroids", required=True)
    a.add_argument("--vectors", required=True)
    a.add_argument("--output", required=True)
    a.add_argument("--chunk", type=int, default=DEFAULT_CHUNK)
    a.set_defaults(func=cmd_assign)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
