# GPUv1-E06 — CUDA K-means content partition for 1M real SIFT descriptors

Seeded K-means (K=32) over the full 1,000,000 x 128 float32 SIFT1M descriptor
set (`input/vectors.npy`), with **all distance, assignment and reduction work
executed as CUDA kernels** on a single RTX 5090. No N x N distance matrix is
ever formed, no prefix-only clustering, no sampling of the training set.

> Debug variant of the formal task: `input/manifest.json` declares
> `scale = debug_only` and `formal_large_tested = false` (native SIFT1M 128-D
> instead of the DEEP1B 96-D/100M reference). This solution does **not** claim
> the reference-large result.

## Entry points

```bash
# train (writes output/centroids.npy, assignments.npy, counts.npy, run.json)
python solution/main.py fit --input input --output output

# assign with pre-trained centroids, fresh process, no re-training
python solution/main.py assign \
    --centroids output/centroids.npy \
    --vectors   input/vectors.npy \
    --output    output/reassigned.npy
```

Optional flags for `fit`: `--k 32 --seed 0 --max-iter 20 --tol 1e-6
--chunk 8192 --init-subsample 262144 --init-iters 20`.

## Artifacts

| file | shape / dtype | content |
|---|---|---|
| `output/centroids.npy`   | (32, 128) float32 | final centroids |
| `output/assignments.npy` | (1000000,) int32  | nearest-centroid label of every vector |
| `output/counts.npy`      | (32,) int64       | cluster sizes, equal to `bincount(assignments)` |
| `output/run.json`        | json              | per-round SSE, seed, synchronized timings, coverage, config, self-checks |
| `output/reassigned.npy`  | (1000000,) int32  | produced by the `assign` sub-command (same labels) |

## Algorithm (all heavy math on the GPU)

1. **Seeding (initialization only).** Seeded k-means++ (`numpy.random.default_rng(seed+101/202)`)
   on a random 262,144-vector subsample, refined with 20 Lloyd iterations on
   that subsample. This only picks the *starting* centroids for the real fit;
   it makes the full-data loop start near the optimum so 20 iterations suffice.
   The seed set and all subsample distances are computed on the GPU.
2. **Lloyd loop on the full 1M vectors**, at most 20 iterations, at least one:
   * `assign` batch (chunk of 8192 rows) — squared Euclidean distances
     `||x - c||^2` via elementwise sub/square + `torch.sum` row reduction over
     a `(chunk, K, D)` tile, then `torch.argmin` over K (CUDA kernels).
   * `update` — centroid sums via `index_add_` (CUDA scatter-reduce), counts via
     `bincount` (CUDA reduction); centroids = sums / counts.
   * **Empty clusters** are handled explicitly every iteration: each empty
     cluster is re-seeded at the farthest point from its assigned centroid
     (deterministic by distance then row index); every occurrence is logged in
     `run.json["empty_cluster_events"]` and per-round `empty_clusters`.
   * Early stop when the assignment is unchanged, or when the relative SSE
     change drops below `--tol`; otherwise it runs the full 20 iterations.
3. **Final assignment strictly against the final centroids** (`assign_and_sse`
   again), and every reported number (counts, SSE) is recomputed from that
   assignment. At a fixed point this is bit-identical to the last update step.

SSE is accumulated in float64 from the float32 per-row squared distances.

## GPU kernels actually launched (PyTorch/CUDA)

* distance: elementwise subtract + multiply + `torch.sum(dim=2)` row reduction
* assignment: `torch.argmin(dim=1)` reduction
* centroid sums: `torch.Tensor.index_add_` scatter-reduce
* counts: `torch.bincount`
* SSE / baseline: `torch.sum` reductions accumulated in float64

The host only slices batches, launches kernels and serializes `.npy`/json; there
is no CPU distance/mean computation in the fit path.

## Measured result (this container, RTX 5090)

```
iters = 20 (cap; not fully converged)   converged = false
final SSE                              = 7.1106e10
single-global-mean-centroid SSE        = 1.4978e11
SSE reduction vs one mean centroid     = 52.53 %   (requirement: >= 5 %)
coverage                               = 1,000,000 / 1,000,000, all labels in [0,32)
counts == bincount(assignments)        = true, sum = 1,000,000
independent nearest-centroid recheck   = 1 mismatch / 1e6 (float32 CPU numpy),
                                         0 / 200,000 with float64
centroid == mean(final cluster)        = max abs residual 2.28,
                                         max relative residual 0.00544 (<= 0.02),
                                         mean relative residual 0.00168
empty clusters                         = none
total synchronized fit time            = 1.68 s (load 1.12 s on top)
```

The small centroid/mean residual is exactly the allowed "last-round deviation
after early stopping": the run hits the 20-iteration cap while a few thousand
boundary points still flip per round, so the centroids are the means of the
previous round's (almost identical) assignment. Re-running `fit` is bit-exact
(same seed, same chunking).

`assign` in a fresh process reproduces `output/assignments.npy` exactly
(`numpy.array_equal == True`).
