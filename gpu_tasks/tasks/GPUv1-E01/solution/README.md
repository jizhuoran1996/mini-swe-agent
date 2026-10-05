# GPUv1-E01 (debug variant)

CUDA float64 materialization of TPC-H **Q1** and **Q6** over the official
`dbgen` SF0.1 `lineitem.npy`, plus a stateless re-query entry point.

This is the **debug** variant declared in `input/manifest.json`
(`scale = debug_only`, `formal_large_tested = false`). It does not claim
the reference-large (SF1000) result.

## Input

`input/lineitem.npy` — float64 `[N, 7]`, columns:

```
0 quantity
1 extendedprice
2 discount
3 tax
4 shipdate_days_since1970
5 returnflag_ascii     ('A'=65 'N'=78 'R'=82)
6 linestatus_ascii     ('F'=70 'O'=79)
```

## Usage

```bash
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output
python solution/main.py query  --state output \
    --start-date 1994-01-01 --end-date 1995-01-01 \
    --discount-low 0.05 --discount-high 0.07 \
    --quantity-limit 24 --output output/query.json
```

`doctor` exits `0` when every required file and CUDA dependency is present,
`78` when anything is missing. `run`/`query` fail hard if CUDA is not visible.

## Query semantics

* **Q1**: `shipdate <= 1998-09-02`, grouped by `(returnflag, linestatus)`,
  emitting `sum_qty, sum_base_price, sum_disc_price, sum_charge,
  avg_qty, avg_price, avg_disc, count` (ordered by the group key).
* **Q6**: `start_date <= shipdate < end_date`,
  `discount_low <= discount <= discount_high`, `quantity < quantity_limit`,
  returning `sum(extendedprice * discount)`.

The `query` subcommand reads only `output/state.json` + `output/dataset.npy`;
it never touches the raw input or any hard-coded answer.

## Verification

Both `run` and `query` recompute the exact same query independently in NumPy
(full data, no sampling) and assert `relative_error <= 1e-8`; `run` aborts with
status `2` if the CUDA and CPU results disagree.

## Outputs

`output/queries.json`, `output/dataset.npy` (reloadable copy of the columns),
`output/state.json`, `output/run.json` (real synchronized timings, device
name, H2D byte count, verification report).

## Honest limitations

* CPU-only environments are rejected — there is no silent fallback.
* Only the debug SF0.1 asset shipped in `input/` is exercised; no network or
  package installation is performed.
* `query --quantity-limit` is compared against the strict `quantity <` TPC-H
  predicate, matching the original Q6.
