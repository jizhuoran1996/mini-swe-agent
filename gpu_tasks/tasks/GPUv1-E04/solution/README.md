# GPUv1-E04 (debug variant) — reloadable taxi fare regressor

Trains an XGBoost 3.0.5 regression model for `fare_amount` on the frozen
`input/` arrays and writes a reloadable model plus validation predictions.

## Environment requirements

* Python with `numpy`
* `xgboost==3.0.5` **compiled with CUDA** (`build_info()['USE_CUDA'] == True`)
* A working CUDA GPU (single RTX 5090 in the grading container)

CPU fallback is not implemented.  Both `train` and `predict` fail closed if
CUDA is missing or if a tiny GPU boosting round cannot be executed.

## Inputs (from `--input`)

| file | meaning |
| --- | --- |
| `train_features.npy` | `(50000, 8)` float32/float64 feature matrix |
| `train_targets.npy` | `(50000,)` `fare_amount` targets |
| `validation_features.npy` | `(5000, 8)` feature matrix |
| `manifest.json` | frozen hashes used by `doctor` verification |

Optional `validation_targets.npy` is used only to *report* validation RMSE/MAE
and the train-mean baseline; it is never used for fitting.  If it is absent the
run proceeds without an eval set (`run.json:eval_set_used == false`).

## Commands

```bash
# inspect inputs/deps without training; exit 0 if ready, 78 otherwise
python solution/main.py doctor --input input

# single required training run
python solution/main.py train --input input --output output

# reuse the persisted model on new rows
python solution/main.py predict \
    --model output/model.json \
    --input input/validation_features.npy \
    --output output/replay_predictions.npy
```

`python solution/main.py --help` prints usage without importing xgboost/numpy.

## Outputs (in `--output`)

* `model.json` — XGBoost JSON booster written by `save_model`.
* `validation_predictions.npy` — `(5000,)` float32 validation predictions.
* `run.json` — input SHA-256 binding, frozen config, `environment` block,
  CUDA-synchronized timing breakdown, and informational validation metrics.

## Frozen training configuration

```json
{"n_estimators": 300, "max_depth": 8, "learning_rate": 0.1,
 "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 1.0,
 "reg_lambda": 1.0, "objective": "reg:squarederror", "eval_metric": "rmse",
 "tree_method": "hist", "device": "cuda", "seed": 42}
```

One run only; no hyper-parameter search, no ensembling.

## Two xgboost compatibility details this build requires

1. **No `device=` on `DMatrix`.**  This container's xgboost build does *not*
   accept the `device` keyword on `DMatrix(...)`.  Device selection goes
   through booster parameters (`device=cuda`) — the supported mechanism;
   xgboost 3.x moves the hist data onto the GPU during training.
2. **Eval sets need labels.**  The default `rmse` evaluation callback compares
   predictions against `info.labels`; passing a label-free DMatrix as an eval
   set aborts training with `preds.Size() == info.labels.Size()` (5000 vs 0).
   We therefore only build an eval set when `validation_targets.npy` exists,
   always attach those labels, and predict afterwards on a fresh label-free
   DMatrix for the exact `(5000,)` output shape.

## Honest limitations

* This is the **debug** scale defined by `input/manifest.json`
  (first 55 000 valid 2019-01 native trips, ordered 50k/5k split).  It is not
  the reference-large annual workload and is not an admission result.
* The debug split is *ordered*, not shuffled, so validation rows are
  temporally adjacent; reported metrics are descriptive only.
* Features are fed as an anonymous `(N, 8)` matrix exactly as provided; no
  feature re-derivation, scaling, or column names are invented.
* Zone/time error tables and parquet audit artefacts from the full reference
  specification are out of scope for this debug variant.
* `predict` also requires CUDA; there is no CPU scoring path.
