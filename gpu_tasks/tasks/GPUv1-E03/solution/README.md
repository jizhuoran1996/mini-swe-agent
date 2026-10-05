# GPUv1-E03 — reloadable HIGGS event classifier (XGBoost CUDA hist)

Binary classifier for real UCI HIGGS events, trained on the provided
`debug_real_100k_train_10k_validation` subset (source rows `[0,100000)` for
training, `[100000,110000)` features for validation). Validation labels are
never read or used; they are not present in `input/`.

## Commands

```bash
python solution/main.py train --input input --output output
python solution/main.py predict --model output/model.json \
    --features input/validation_features.npy \
    --output output/validation_predictions.npy
python solution/selfcheck.py --input input --output output   # optional self-check
```

`train` loads `input/{train_features,train_labels}.npy`, trains **on the GPU
with XGBoost CUDA histogram** (`device=cuda:0`, `tree_method=hist`,
`objective=binary:logistic`, fixed `seed=42`), writes:

* `output/model.json` — full model, reloadable with the standard
  `xgboost.Booster().load_model()` API (no pickle);
* `output/validation_predictions.npy` — `(10000,)` float32 probabilities in
  `[0,1]`, same order as `input/validation_features.npy`;
* `output/training_manifest.json` — parameters, framework/device versions,
  input SHA-256 hashes (matching `input/manifest.json`), row counts, tree
  count and CUDA-synchronized stage timings.

`predict` only needs a saved `model.json` and a feature matrix — it does not
touch the training inputs, so it works after the original data is removed.

## Training configuration

* GPU histogram (`device=cuda:0`, `tree_method=hist`, `max_bin=256`), 28
  features, `QuantileDMatrix` sketch built once and reused for the internal
  validation matrix (`ref=`).
* Stage 1: seeded 10k-row internal split of the training rows (seeded random
  permutation) with `early_stopping_rounds=50` over up to 1200 rounds selects
  the number of trees; no validation labels are involved.
* Stage 2: final model retrained on **all 100,000** training rows with that
  number of rounds (`eta=0.06`, `max_depth=7`, `subsample=0.9`,
  `colsample_bytree=0.8`, `min_child_weight=5`, `lambda=1`, `seed=42`).
* The selected model used 313 trees; internal split AUC was 0.8111. A separate
  sanity run (not a deliverable) trained on rows `[0,80000)` and evaluated on
  the contiguous block `[80000,100000)` — the same prefix/contiguous-block
  regime as the real split — giving AUC 0.812, so performance is far above the
  0.65 requirement.
* Predictions are taken on the GPU during training for a cross-check
  (max `|gpu-cpu|` ≈ 1.2e-7), while the delivered predictions are produced by a
  fresh reload of `model.json` through the standard CPU API — exactly what the
  evaluator recomputes (observed difference 0.0). The JSON model format does
  not persist the runtime device, so a reloaded `Booster` predicts on CPU by
  default and the artifact is fully device-agnostic.

## Files

* `main.py` — `train` / `predict` CLI (all training and data handling).
* `selfcheck.py` — independent self-check: reloads `model.json` in a fresh
  process, re-predicts, compares with the stored `.npy` under
  `atol=1e-6, rtol=1e-5`, and validates manifest/hashes/ranges.
