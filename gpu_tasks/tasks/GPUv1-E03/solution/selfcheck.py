#!/usr/bin/env python
"""Self-check for the delivered GPUv1-E03 artifacts.

Reloads output/model.json with the plain XGBoost API (fresh process), scores the
validation features and compares against the stored prediction file, then
verifies the training manifest and artifact shapes/ranges.

Usage: python solution/selfcheck.py [--output output] [--input input]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np
import xgboost as xgb


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="input")
    ap.add_argument("--output", default="output")
    args = ap.parse_args()

    model_path = os.path.join(args.output, "model.json")
    pred_path = os.path.join(args.output, "validation_predictions.npy")
    man_path = os.path.join(args.output, "training_manifest.json")
    feat_path = os.path.join(args.input, "validation_features.npy")

    checks: list[tuple[str, bool, str]] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    for p in (model_path, pred_path, man_path):
        chk(f"exists:{os.path.basename(p)}", os.path.isfile(p), p)

    x = np.load(feat_path)
    stored = np.load(pred_path)
    chk("pred_shape", stored.shape == (x.shape[0],), str(stored.shape))
    chk("pred_dtype_float", np.issubdtype(stored.dtype, np.floating), str(stored.dtype))
    chk("pred_finite", bool(np.isfinite(stored).all()))
    chk("pred_range", bool((stored >= 0).all() and (stored <= 1).all()),
        f"[{stored.min():.6f},{stored.max():.6f}]")
    chk("pred_not_constant", float(stored.std()) > 1e-6, f"std={stored.std():.6g}")

    bst = xgb.Booster()
    bst.load_model(model_path)
    bst.set_param({"device": "cpu"})
    recomputed = np.asarray(bst.predict(xgb.DMatrix(x.astype(np.float32))), dtype=np.float64)
    diff = np.abs(recomputed - stored.astype(np.float64))
    tol = 1e-6 + 1e-5 * np.abs(recomputed)
    chk("reload_std_api_pred_match", bool((diff <= tol).all()),
        f"max_abs={diff.max():.3e} (atol=1e-6, rtol=1e-5)")
    chk("reload_num_trees_ge32", bst.num_boosted_rounds() >= 32,
        f"trees={bst.num_boosted_rounds()}")

    with open(man_path) as fh:
        man = json.load(fh)
    chk("manifest_sha256_model", man.get("model_sha256") == sha256_file(model_path))
    chk("manifest_sha256_inputs",
        all(man["input_sha256"][k] == sha256_file(os.path.join(args.input, k))
            for k in man["input_sha256"]))
    chk("manifest_train_rows", man.get("train_rows") == 100000, str(man.get("train_rows")))
    chk("manifest_trees_ge32", man.get("num_trees", 0) >= 32, str(man.get("num_trees")))
    chk("manifest_train_on_cuda",
        man["training_params"].get("device") == "cuda:0"
        and man["training_params"].get("tree_method") == "hist")
    chk("manifest_no_validation_labels", man.get("validation_labels_used") is False)
    chk("manifest_stage_times", all(man.get("stage_seconds", {}).get(k) is not None
                                    for k in ("final_train", "gpu_predict", "reload_cpu_predict")))

    ok_all = True
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name:34s} {detail}")
        ok_all &= ok
    print(f"\n{'ALL CHECKS PASSED' if ok_all else 'SOME CHECKS FAILED'} "
          f"({sum(c[1] for c in checks)}/{len(checks)})")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
