Single-file CLI (`solution/main.py`, <400 LOC). Lazy torch import keeps
`--help` and `doctor` free of model/GPU loading. GPU work uses genuine float64
torch tensors: Q1 filters on `shipdate`, hashes `(returnflag, linestatus)`
with `torch.unique(return_inverse=True)` and does eight `scatter_add_`
reductions; Q6 performs a masked float64 sum on device. Every run/query is
independently recomputed with NumPy and gated at `rel_err <= 1e-8`. Outputs:
`queries.json`, `dataset.npy`, `state.json`, `run.json`.