# GPUv1-E02 — reusable Criteo_x1 recommendation feature pipeline (debug variant)

Build a persisted, reusable preprocessor for the genuine `reczoo/Criteo_x1`
subset shipped in `input/` (1000 training rows, 100 held-out rows, 39 columns).

## Usage

```bash
# Inspect required files and dependencies without running anything heavy
python solution/main.py doctor --input input

# Fit the preprocessor on the training split and materialize artifacts
python solution/main.py fit --input input --output output

# Re-apply the saved preprocessor to any new JSONL file
python solution/main.py transform \
    --preprocessor output/preprocessor.json \
    --input input/validation.jsonl \
    --output output/validation_features_again.npy

# Help works without importing torch / CUDA
python solution/main.py --help
```

## Schema contract

`input/schema.json` is honored exactly via these keys:

* `dense_columns`  → the 13 numerical columns (`I1` … `I13`)
* `categorical_columns` → the 26 categorical columns (`C1` … `C26`)
* `label_column` → the label field name (`label`)

All list keys are looked up case-insensitively and also accept the common
aliases (`dense_features`, `numerical`, `cat_features`, `sparse_features`, …).

## Algorithm (exactly per spec)

* **Numerical columns (13).** A missing value is filled with `0`. The training
  mean and training **population** standard deviation (`ddof=0`) are computed on
  the filled values; a zero standard deviation is replaced by `1`. Every value
  is then mapped to `(x - mean) / std`.
* **Categorical columns (26).** For each column the distinct non-missing string
  values observed in the **training** split are sorted lexicographically and
  assigned integer ids starting at `1`. A missing value or an unseen value maps
  to id `0`.
* **Feature tensor.** `[13 standardized numerics | 26 category ids]` as
  `float32`, row-major, one row per input record, in the schema order
  (`I1..I13` then `C1..C26`).
* **CUDA.** The numerical statistics, the standardization and the final
  feature-tensor assembly are executed on `cuda:0`. Category dictionaries are
  built on the CPU. `torch.cuda.synchronize()` brackets every GPU section so
  the recorded timings are real.

## Outputs of `fit`

| file | content |
| --- | --- |
| `output/preprocessor.json` | fitted means, stds and per-column category dictionaries |
| `output/train_features.npy` | float32 `(1000, 39)` |
| `output/validation_features.npy` | float32 `(100, 39)` |
| `output/train_labels.npy` | int64 `(1000,)` |
| `output/validation_labels.npy` | int64 `(100,)` — written **only when** the input validation rows carry labels |
| `output/run.json` | device info, shapes, category domain sizes, real timings |

If the validation split carries no label field, `validation_labels.npy` is
omitted (never fabricated).

`preprocessor.json` is fully self-describing, so `transform` reloads it and
reapplies the identical mapping to new data, including the unknown / missing
`-> 0` rule.

## Exit codes

* `doctor` returns `78` if any required input file or dependency (numpy, torch,
  CUDA) is absent, and `0` otherwise.
* `fit` / `transform` raise (nonzero exit) if CUDA is unavailable — this task
  must not silently fall back to CPU.

## Honest limitations

* This is the **debug variant**: 1000 train / 100 held-out rows of a genuine
  Criteo_x1 subset, with a deliberately small categorical domain. It does **not**
  reproduce the reference-large workload, which is untested here.
* Single required run; no hyperparameter search, no ensembling, no mock or
  randomized weights. Everything is derived from the supplied real rows.
* No network access, no package installation, no host file access. Inputs are
  read-only; all artifacts are written under `output/`.
* `transform` assumes the same JSON string representation of categorical values
  as was used during `fit`; it maps anything unseen to `0` per the spec.
