`doctor --input input` performs read-only inspection:

1. Presence of `train_features.npy`, `train_targets.npy`,
   `validation_features.npy`, `manifest.json`.
2. SHA-256 of each `.npy` recomputed and compared with `manifest.json:files`.
3. `numpy` and `xgboost` importability.
4. `xgboost.build_info()['USE_CUDA']` and `torch.cuda.is_available()`.

It never trains, never predicts, and returns exit code 78 if any item is
missing/unusable, 0 otherwise.  A missing-input report is never treated as a
solved task.
