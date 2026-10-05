# GPUv1-E05 (debug variant) - exact CUDA L2 retrieval index over native SIFT1M

## What this is

A real, GPU-resident **exact** squared-L2 top-k index over the provided
`input/base.npy` (1,000,000 x 128, native SIFT1M) with an independent set of
`input/queries.npy` (10,000 x 128). All distance computation happens on CUDA.
The index is persisted to disk in a fully reloadable form and can be queried
with new vectors without the original input directory.

This is the **debug_only** variant declared in `input/manifest.json`
(`"scale": "debug_only"`, `"formal_large_tested": false`). It does **not**
claim to be the reference-large 100M-descriptor BIGANN task; it is the
1M-vector native SIFT1M instantiation of the same retrieval workflow.

## Commands

```
python solution/main.py build  --input input --output output
python solution/main.py query  --index output/index --queries PATH.npy --output DIR --k 10
python solution/main.py serve  --index output/index --port 8000 [--host 127.0.0.1]
python solution/main.py doctor --input input [--output-dir output]
```

`python solution/main.py --help` prints usage and does not import torch or
load any index.

### build

1. Verifies `base.npy` / `queries.npy` exist and (when `manifest.json` is
   present) that their SHA-256 hashes match the frozen manifest.
2. Requires a working CUDA device; aborts if CUDA is unavailable.
3. Writes the persisted database to `output/index/`:
   * `index/vectors.npy` - the full 1,000,000 x 128 float database (memmap-able)
   * `index/meta.json`   - format, ntotal, dim, dtype, metric, sha256 of vectors
4. Loads the database into GPU memory (float64) and answers **all 10,000
   queries** exactly.
5. Writes `output/indices.npy` (10000, 10) int64 and
   `output/squared_distances.npy` (10000, 10) float32.
6. Runs an independent float64 CPU brute-force oracle on a subset of queries
   and records recall / distance agreement in `output/run.json`.

### query

Loads `--index` only (never the original `input/`), runs the same exact CUDA
search on an arbitrary `(n, 128)` `.npy` array, and writes
`indices.npy` / `squared_distances.npy` / `run.json` into `--output`.

### serve

Loads the index onto the GPU up front, then serves HTTP:

* `GET /health` -> `{"status":"ok","cuda":true,"device":...,"ntotal":...,"dim":128,...}`
* `POST /search` with body `{"vectors": [[...128 floats...], ...], "k": 10}`
  -> `{"indices": [[...]], "squared_distances": [[...]], "k": 10, ...}`

`READY` is printed once the socket is bound. `SIGTERM`/`SIGINT` shut the
server down cleanly. The index stays resident, so repeated queries after idle
periods are answered from GPU memory with no reload.

### doctor

Inspects exactly the files and dependencies the job needs, without performing
any training or inference:

* input directory and `base.npy` / `queries.npy` / `manifest.json` presence
* SHA-256 agreement with the manifest
* array shape/dtype readability
* numpy / torch importability and real CUDA availability plus a test allocation
* output directory writability

It prints a JSON report, lists every missing item, exits **78** (EX_CONFIG) if
anything is missing or unavailable and **0** otherwise.

## Algorithm and memory behaviour

For every query tile `Q` (up to ~384 rows) the engine sweeps the database in
tiles `B` (262,144 rows) and computes

```
d2 = (q2 + b2) - 2 * Q @ B^T
```

with `torch.addmm` in **float64**. Each tile is at most ~768 MiB, so a full
`N x N` matrix is never materialised, and per-tile top-k results are merged
into a running top-k with a stable sort. The tile sizes adapt to free device
memory reported by `torch.cuda.mem_get_info`. All GPU work is bracketed by
`torch.cuda.synchronize()` before timings are read, so `run.json` records real
synchronised device timings.

float64 accumulation makes the squared distances exact for SIFT descriptors
(uint8 values stored as floats): every partial product and partial sum is an
integer below 2^53.

## Outputs

```
output/
  index/{vectors.npy, meta.json}
  indices.npy            (nq, 10) int64
  squared_distances.npy  (nq, 10) float32
  run.json               task id, GPU info, input hashes, config, timings,
                         self-check recall, output inventory
```

## Honest limitations

* Debug scale only: 1M vectors / 10k queries. The formal reference-large
  workload (100M BIGANN prefix, IVF-PQ, GPU->CPU serialisation) is **not**
  implemented and is **not** claimed.
* The index is an exact brute-force database, not a compressed IVF-PQ
  structure; it trades the 1M-scale memory footprint for zero approximation
  error. At 100M scale this representation would not fit a single GPU and
  would need quantisation, which is out of scope here.
* `serve` uses the Python standard-library HTTP server with a single GPU lock;
  it is a correctness-oriented worker, not a tuned high-QPS service.
* Reload is validated by re-reading `index/vectors.npy` and re-running the
  exact search; it is an application-level reload, not a CUDA context or VM
  snapshot.
* No reference-large measurements are reported because none were produced.
