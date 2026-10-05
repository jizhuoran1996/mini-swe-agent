# GPUv1-E07 — GPU PageRank on the SNAP Twitter ego-network union

## Run

```bash
python solution/main.py rank --input input --output output
# continue an interrupted / partially converged run on the SAME graph:
python solution/main.py rank --input input --output output --resume output/state.npz
```

Optional flags: `--alpha` (default 0.85), `--tol` (default 1e-7), `--max-iter`
(default 1000), `--device` (default `auto` → CUDA, required), `--no-sort`.

## Model

`input/edges.npy` has shape `(2420766, 2)` and holds every directed follow edge
of the union graph as dense node indices; `input/node_ids.npy` maps dense row
index → original Twitter id (row order == rank order). Every input row is one
edge, so parallel edges are counted with their multiplicity exactly as the raw
SNAP file stores them; nothing is deduplicated, added or fabricated.

Power iteration (float64, uniform start `1/N`):

```
r_{k+1} = alpha * (A_hat^T r_k) + alpha * (sum(r_k over dangling) / N) + (1 - alpha) / N
A_hat[i, j] = 1 / outdeg(i)   (outdeg counts parallel edges)
```

Iteration stops when `||r_{k+1} - r_k||_1 < 1e-7` or after 1000 iterations.

## Where the work happens

* The main iteration runs on the CUDA device with PyTorch `float64`:
  * per-edge masses are gathered on the GPU: `r[src] * inv_deg[src]`,
  * edge contributions are propagated with a GPU scatter-add
    (`Tensor.index_add_` on the destination indices),
  * the dangling mass, the L1 difference and the teleport terms are GPU
    reductions (`Tensor.sum` / `Tensor.abs`).
* The CPU only loads the arrays, hashes the graph, serialises artifacts and runs
  an **independent SciPy oracle as a self-check** (it never produces the
  delivered ranks). No CPU PageRank result is copied to the GPU.

## Artifacts (written to `--output`)

| file | content |
| --- | --- |
| `ranks.npy` | `float64 (81306,)` PageRank vector, aligned with `node_ids.npy` row order |
| `top_nodes.json` | top-100 by rank descending, ties broken by original node id ascending (`top_nodes` objects + `top_node_ids`) |
| `state.npz` | `ranks`, `iteration` (total), `alpha`, `graph_hash`, plus `n`, `tol`, `max_iter`, `converged`, `last_l1_diff` |
| `run.json` | full run metadata: device, iterations, convergence, residuals, graph hash, oracle self-check, timings |

## Resume semantics

`--resume` accepts a `state.npz` path. The stored `graph_hash` (canonical sha256
of `node_ids` + the sorted edge multiset) and `alpha`/`n` are validated against
the current input; a mismatch aborts with an error instead of silently
continuing on a different graph. The rank vector and the number of already
performed iterations are restored, so the graph and the id mapping are byte-for-
byte the ones of the original run and only the iteration count advances.

## Verified (RTX 5090)

* 72 iterations to `||Δr||_1 = 8.8e-8` (`converged=True`), ~1.5 s.
* `sum(ranks) = 1.0`, `min(ranks) > 0`.
* Independent SciPy oracle: fixed-point L1 residual `7.45e-8 < 2e-6`,
  `||ranks - oracle||_1 = 3.5e-7 < 1e-5`.
* Resuming a converged run adds one iteration and reproduces the ranks to
  `<= 7.5e-8` L1; resuming a 25-iteration partial state converges to the fresh
  result within `4e-16` L1.
