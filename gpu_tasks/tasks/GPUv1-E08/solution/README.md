# GPUv1-E08 (debug variant) - GPU community inventory

Communities + cross-community edge inventory for the SNAP Facebook ego-network
union graph shipped in `input/` (4039 nodes, 88234 undirected edges, from
`facebook_combined.txt.gz`; see `input/manifest.json`).

## Commands

```bash
# main run (requires CUDA; hard-fails on CPU-only hosts)
python solution/main.py cluster --input input --output output

# fresh-process recomputation from the saved partition only
python solution/main.py report --input input \
    --communities output/communities.npy --output output/reloaded_report

# environment/input inspection, never executes the algorithm
python solution/main.py doctor --input input      # exit 0 if available, 78 if not
```

`cluster` accepts `--seed` (default 20240517), `--chunk-size` (default 128) and
`--max-sweeps` (default 60).

## Algorithm (real CUDA compute)

The undirected simple graph is built as symmetric CUDA arc lists
(`src`/`dst`, `2m = 176468` arcs) with degrees via `bincount`. Community
detection is a **chunked Louvain local-moving (PLM/Louvain phase-1)** run
entirely on device under a fixed seed:

* nodes are visited in a seeded `torch.randperm` order in chunks of 128;
* for each chunk the dense weight block `W[i, c] = #edges from i into community c`
  is produced with `scatter_add_` on linear CUDA indices,
  `k_iA` with `gather`, and the exact gain
  `dQ(i->B) = (k_iB - k_iA)/m - k_i (tot_B - tot_A + k_i) / (2 m^2)`
  is evaluated for every community in one dense kernel;
* the best strictly-positive move is applied (`index_add_` on community totals,
  `index_copy_` on labels); sweeps repeat until no node moves or `--max-sweeps`.
* after every sweep the **standard undirected modularity**
  `Q = sum_c [ e_c/m - (tot_c/2m)^2 ]` is recomputed on the GPU and the best
  partition seen is kept.

Labels are then deterministically renumbered by community size and the
inventory is aggregated with CUDA `bincount`; the cross-community mask is
`comm[u] != comm[v]` over the original edge rows.

## Outputs (`output/`)

| file | contents |
|---|---|
| `communities.npy` | `(4039,)` int64 community id per dense node index |
| `community_summary.json` | per-community node counts, internal edge counts, degree sums, totals, modularity |
| `cross_edges.npy` | `(C,2)` int64 original dense-index edges whose endpoints are in different communities, each source edge exactly once |
| `state.npz` | partition, degrees, modularity/move history, hyper-parameters, CPU+CUDA RNG states |
| `run.json` | device/driver versions, algorithm config, synchronized stage timings, memory peaks, hashes, all self-checks |

`report` writes `community_summary.json`, `cross_edges.npy` and `report.json`
into its `--output` directory and re-verifies coverage, community count,
modularity floor and the `internal + cross == m` identity with a pure-NumPy
recomputation (intentionally a different code path from the GPU run).

## Host note (cuDNN LD_LIBRARY_PATH mismatch)

The graph workload does not use cuDNN. Some hosts export an `LD_LIBRARY_PATH`
whose cuDNN is older than the version PyTorch was built against, which makes a
plain `torch.backends.cudnn.version()` call raise. All device metadata probes
(torch/cuda/cuDNN versions, device name, capability, memory counters, RNG state
capture) are therefore individually guarded: a failing probe degrades to a
short `unavailable (...)` string and is recorded in `run.json`, but never aborts
an otherwise successful CUDA computation.

## Checks performed before declaring success

* every node has exactly one community id; ids non-negative;
* `>= 2` non-empty communities, not all singletons, not a single community;
* standard undirected modularity `>= 0.25` (Facebook ego-union typically lands
  near 0.75-0.85);
* NumPy re-aggregation reproduces the GPU sizes, internal-edge counts and
  modularity bit-for-bit (`<1e-9`) and the saved cross-edge file equals the
  recomputed one;
* `internal_edges + cross_edges == 88234`.

## Honest limitations

* This is the **debug-scale union ego graph**, not the full Friendster graph;
  the formal large-scale run is explicitly out of scope here
  (`reference_large` is not claimed).
* The implementation is single-GPU, single-level Louvain local moving (no
  graph coarsening / second level). It maximizes modularity greedily and can
  differ from other Louvain implementations in the exact partition; label
  permutations are equivalent by construction (labels are size-sorted).
* Chunked (semi-parallel) move application may theoretically differ from a
  strictly sequential Louvain ordering; the best-modularity sweep is kept, so
  the reported partition is never worse than the initial singleton state.
* `report` is a lightweight NumPy verification path and does not use CUDA; the
  CUDA requirement applies to the `cluster` workload.
* No network access, no package installation, no CPU fallback and no synthetic
  or mock graph/weights are used; all inputs are the provided local `.npy`
  arrays.
