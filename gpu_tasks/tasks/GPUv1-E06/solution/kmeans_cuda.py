"""
GPU (CUDA / PyTorch) k-means core for the GPUv1-E06 content-partition task.

Everything numerically heavy runs as real CUDA kernels launched by PyTorch:

  * batched squared-Euclidean distances  : chunked (x - c)^2 elementwise + CUDA
    row reduction (`sum`), never an N x N matrix.
  * assignment (argmin over K)           : CUDA min/argmin reduction kernel.
  * centroid sums / counts               : `index_add_` (CUDA scatter-reduce)
                                           and `bincount` (CUDA reduction).
  * SSE / objective                      : chunked CUDA reductions accumulated
                                           in float64.

The host (CPU) only orchestrates the launches and serializes the results.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

DEFAULT_CHUNK = 8192          # rows per CUDA launch batch
DTYPE = torch.float32


# ----------------------------------------------------------------------------
# device / data helpers
# ----------------------------------------------------------------------------
def get_device() -> torch.device:
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for this task: no CUDA-capable device visible."
        )
    return torch.device("cuda")


def sync(device: torch.device) -> None:
    """Explicit device synchronization used for honest wall-clock timing."""
    torch.cuda.synchronize(device)


def load_vectors(path: str, device: torch.device) -> torch.Tensor:
    """Load an (N, D) float32 .npy descriptor matrix onto the GPU."""
    arr = np.load(path, mmap_mode="r")
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D vector matrix, got shape {arr.shape}")
    host = np.array(arr, dtype=np.float32, copy=True, order="C")
    x = torch.from_numpy(host).to(device)      # one H2D copy of the whole matrix
    del host
    return x


# ----------------------------------------------------------------------------
# CUDA distance / assignment / reduction
# ----------------------------------------------------------------------------
def assign_and_sse(
    x: torch.Tensor,
    centroids: torch.Tensor,
    chunk: int = DEFAULT_CHUNK,
    want_sse: bool = True,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Nearest-centroid assignment (and SSE) for every row of `x`.

    Distances are computed batch-by-batch as ||x_i - c_k||^2 on the GPU; the
    biggest temporary is (chunk, K, D) -- there is no N x N work anywhere.
    SSE is accumulated in float64 for a trustworthy objective value.
    """
    n = x.shape[0]
    k = centroids.shape[0]
    assign = torch.empty(n, dtype=torch.int64, device=x.device)
    sse = torch.zeros((), dtype=torch.float64, device=x.device)
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        xb = x[s:e]
        diff = xb.unsqueeze(1) - centroids.unsqueeze(0)      # (b, K, D)
        dist = torch.sum(diff * diff, dim=2)                 # (b, K) CUDA reduction
        a = torch.argmin(dist, dim=1)                        # (b,)
        assign[s:e] = a
        if want_sse:
            sse += dist.gather(1, a.unsqueeze(1)).squeeze(1).double().sum()
    return assign, sse


def assign_chunked(
    x: torch.Tensor, centroids: torch.Tensor, chunk: int = DEFAULT_CHUNK
) -> torch.Tensor:
    """Assignment only (used by the `assign` sub-command)."""
    return assign_and_sse(x, centroids, chunk=chunk, want_sse=False)[0]


def centroid_sums_counts(
    x: torch.Tensor, assign: torch.Tensor, k: int, chunk: int = DEFAULT_CHUNK
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Per-cluster sums and counts, computed by CUDA reduction kernels."""
    d = x.shape[1]
    sums = torch.zeros((k, d), dtype=DTYPE, device=x.device)
    idx = assign.to(torch.int64)
    for s in range(0, x.shape[0], chunk):
        e = min(s + chunk, x.shape[0])
        sums.index_add_(0, idx[s:e], x[s:e])      # CUDA scatter-reduce
    counts = torch.bincount(idx, minlength=k)     # CUDA reduction
    return sums, counts


def mean_centroid_sse(x: torch.Tensor, chunk: int = DEFAULT_CHUNK) -> torch.Tensor:
    """SSE of the single global-mean centroid (float64)."""
    mean = x.double().mean(dim=0)
    sse = torch.zeros((), dtype=torch.float64, device=x.device)
    for s in range(0, x.shape[0], chunk):
        e = min(s + chunk, x.shape[0])
        diff = x[s:e].double() - mean
        sse += (diff * diff).sum()
    return sse


# ----------------------------------------------------------------------------
# initialization (seeded k-means++, computed on the GPU)
# ----------------------------------------------------------------------------
def kmeanspp_init(
    x: torch.Tensor,
    k: int,
    seed: int,
    subsample: int = 65536,
    device: Optional[torch.device] = None,
) -> torch.Tensor:
    """Seeded k-means++ initialization on a random subsample (GPU distances)."""
    device = x.device if device is None else device
    n = x.shape[0]
    rng = np.random.default_rng(seed + 101)
    m = int(min(subsample, n))
    sub_idx = np.sort(rng.choice(n, size=m, replace=False))
    sub = x[torch.from_numpy(sub_idx).to(device)]          # (m, D) on GPU

    cent = torch.empty((k, x.shape[1]), dtype=DTYPE, device=device)
    first = int(rng.integers(m))
    cent[0] = sub[first]
    d2 = ((sub - cent[0]) ** 2).sum(dim=1)                 # (m,) CUDA
    for j in range(1, k):
        probs = d2.clamp_min(0).cpu().numpy().astype(np.float64)
        total = probs.sum()
        if not np.isfinite(total) or total <= 0.0:
            probs = np.full(m, 1.0 / m)
        else:
            probs = probs / total
        pick = int(rng.choice(m, p=probs))
        cent[j] = sub[pick]
        nd = ((sub - cent[j]) ** 2).sum(dim=1)
        d2 = torch.minimum(d2, nd)                         # CUDA elementwise min
    return cent


def pretrained_init(
    x: torch.Tensor,
    k: int,
    seed: int,
    subsample: int = 262144,
    refine_iters: int = 20,
    chunk: int = DEFAULT_CHUNK,
) -> Tuple[torch.Tensor, Dict]:
    """Seeded initialization: k-means++ + Lloyd refinement on a random subsample.

    This is *initialization only* -- it produces the starting centroids for the
    real full-data Lloyd loop.  All arithmetic (subsample gather, distances,
    reductions) happens on the GPU.  Returns (centroids, info).
    """
    device = x.device
    n = x.shape[0]
    rng = np.random.default_rng(seed + 202)
    m = int(min(subsample, n))
    idx = np.sort(rng.choice(n, size=m, replace=False))
    sub = x[torch.from_numpy(idx.astype(np.int64)).to(device)]

    c = kmeanspp_init(sub, k, seed, subsample=m, device=device)
    sse_hist: List[float] = []
    for t in range(int(refine_iters)):
        a, sse = assign_and_sse(sub, c, chunk=chunk, want_sse=True)
        sums, counts = centroid_sums_counts(sub, a, k, chunk=chunk)
        reinit_empty_clusters(sub, c, a, counts, chunk=chunk)
        with torch.no_grad():
            ne = counts > 0
            c = torch.where(
                ne.unsqueeze(1),
                sums / counts.clamp_min(1).unsqueeze(1).to(DTYPE),
                c,
            ).contiguous()
        sse_hist.append(float(sse.item()))
    info = {
        "subsample": m,
        "subsample_seed": seed + 202,
        "refine_iters": int(refine_iters),
        "sse_history": sse_hist,
    }
    return c, info


# ----------------------------------------------------------------------------
# empty-cluster handling
# ----------------------------------------------------------------------------
def reinit_empty_clusters(
    x: torch.Tensor,
    centroids: torch.Tensor,
    assign: torch.Tensor,
    counts: torch.Tensor,
    chunk: int = DEFAULT_CHUNK,
) -> List[int]:
    """Re-seed empty clusters with the farthest points from their centroid.

    Returns the list of cluster ids that were empty (explicit handling is
    recorded in run.json).  Deterministic: ties broken by smallest row index.
    """
    empty = torch.nonzero(counts == 0, as_tuple=False).flatten()
    if empty.numel() == 0:
        return []
    n = x.shape[0]
    far = torch.empty(n, dtype=DTYPE, device=x.device)
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        diff = x[s:e] - centroids[assign[s:e]]
        far[s:e] = (diff * diff).sum(dim=1)
    take = int(empty.numel())
    # torch.topk is deterministic for a given tensor/argsort order.
    _, idx = torch.topk(far, take, largest=True, sorted=True)
    idx = idx.cpu().tolist()
    used = set()
    chosen: List[int] = []
    for row in idx:
        if row not in used:
            used.add(row)
            chosen.append(row)
        if len(chosen) == take:
            break
    for j, cid in enumerate(empty.cpu().tolist()):
        row = chosen[j] if j < len(chosen) else chosen[-1]
        centroids[cid] = x[row]
    return empty.cpu().tolist()


# ----------------------------------------------------------------------------
# the Lloyd loop
# ----------------------------------------------------------------------------
def fit_kmeans(
    x: torch.Tensor,
    k: int,
    seed: int,
    max_iter: int = 20,
    chunk: int = DEFAULT_CHUNK,
    tol: float = 1e-6,
    subsample: int = 65536,
    init_subsample: int = 262144,
    init_iters: int = 20,
    log=print,
) -> Dict:
    """Seeded Lloyd k-means fully on the GPU.

    Loop invariant / ordering:
        iteration t: assign against centroids_t, then centroids_{t+1} = means
        of that assignment (+ empty-cluster re-seeding).
    The loop runs at least once (>=1 real Lloyd update) and stops early when
    the assignment no longer changes, or when both the relative centroid move
    and the relative SSE change fall below `tol`.
    """
    device = x.device
    n, d = x.shape
    t_start = time.perf_counter()
    sync(device)

    t0 = time.perf_counter()
    if init_subsample and init_subsample > 0 and init_iters > 0:
        centroids, init_info = pretrained_init(
            x, k, seed, subsample=init_subsample,
            refine_iters=init_iters, chunk=chunk,
        )
    else:
        centroids = kmeanspp_init(x, k, seed, subsample=subsample, device=device)
        init_info = {"subsample": int(min(subsample, n)), "refine_iters": 0,
                     "sse_history": []}
    sync(device)
    t_init = time.perf_counter() - t0

    history: List[Dict] = []
    empty_events: List[Dict] = []
    prev_assign: Optional[torch.Tensor] = None
    prev_sse: Optional[float] = None
    converged = False
    n_done = 0

    for it in range(max_iter):
        t0 = time.perf_counter()
        assign, sse = assign_and_sse(x, centroids, chunk=chunk, want_sse=True)
        sync(device)
        t_assign = time.perf_counter() - t0

        t0 = time.perf_counter()
        sums, counts = centroid_sums_counts(x, assign, k, chunk=chunk)
        empty = reinit_empty_clusters(x, centroids, assign, counts, chunk=chunk)
        with torch.no_grad():
            nonempty = counts > 0
            centroids = torch.where(
                nonempty.unsqueeze(1),
                sums / counts.clamp_min(1).unsqueeze(1).to(DTYPE),
                centroids,
            ).contiguous()
        sync(device)
        t_update = time.perf_counter() - t0

        sse_val = float(sse.item())
        changed = int(n) if prev_assign is None else int(
            (assign != prev_assign).sum().item()
        )
        history.append(
            {
                "iter": it,
                "sse": sse_val,
                "changed": changed,
                "counts": counts.cpu().tolist(),
                "empty_clusters": empty,
                "time_assign_s": t_assign,
                "time_update_s": t_update,
            }
        )
        if empty:
            empty_events.append({"iter": it, "clusters": empty})
        log(
            f"[fit] iter {it:2d}  sse={sse_val:.6f}  changed={changed:8d}  "
            f"empty={len(empty)}  t_assign={t_assign:.3f}s t_update={t_update:.3f}s"
        )
        n_done = it + 1

        rel_sse = (
            abs(sse_val - prev_sse) / max(abs(prev_sse), 1e-30)
            if prev_sse is not None
            else float("inf")
        )
        prev_assign, prev_sse = assign, sse_val

        if changed == 0:
            converged = True
            break
        if it >= 1 and rel_sse < tol:
            converged = True
            break

    # ---- final assignment strictly against the final centroids -------------
    t0 = time.perf_counter()
    final_assign, final_sse = assign_and_sse(x, centroids, chunk=chunk, want_sse=True)
    sync(device)
    t_final = time.perf_counter() - t0

    final_counts = torch.bincount(final_assign, minlength=k)
    # Independent cross-check of the centroid means (float64 one-hot GEMM on GPU).
    with torch.no_grad():
        oh = torch.zeros((n, k), dtype=torch.float64, device=device)
        oh[torch.arange(n, device=device), final_assign] = 1.0
        sums64 = oh.t().matmul(x.double())
        counts64 = oh.sum(dim=0)
        means64 = sums64 / counts64.clamp_min(1).unsqueeze(1)
    mean_res = (centroids.double() - means64).norm(dim=1)
    mean_ref = means64.norm(dim=1).clamp_min(1e-12)
    rel_res = mean_res / mean_ref

    base_sse = mean_centroid_sse(x, chunk=chunk)
    sync(device)
    t_total = time.perf_counter() - t_start

    result = {
        "centroids": centroids.contiguous(),
        "assignments": final_assign,
        "counts": final_counts,
        "final_sse": float(final_sse.item()),
        "baseline_sse": float(base_sse.item()),
        "history": history,
        "empty_events": empty_events,
        "converged": converged,
        "n_iter": n_done,
        "timing": {
            "sync": True,
            "init_s": t_init,
            "final_assign_s": t_final,
            "total_fit_s": t_total,
        },
        "init": init_info,
        "mean_residual": {
            "max_abs": float(mean_res.max().item()),
            "max_rel": float(rel_res.max().item()),
            "mean_rel": float(rel_res.mean().item()),
        },
    }
    return result
