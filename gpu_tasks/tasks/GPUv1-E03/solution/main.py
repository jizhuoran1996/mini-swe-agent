#!/usr/bin/env python
"""GPUv1-E03: train a reloadable HIGGS event classifier with XGBoost CUDA hist.

Subcommands
-----------
train   : fit on input/{train_features,train_labels}.npy with XGBoost
          (device=cuda:0, tree_method=hist, objective=binary:logistic),
          save output/model.json, predict input/validation_features.npy
          into output/validation_predictions.npy and write
          output/training_manifest.json.
predict : reload a saved model.json with the standard XGBoost API and write
          probabilities for a feature matrix as a .npy array.

Only the inputs in ``--input`` are read; validation labels are never used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time

import numpy as np
import xgboost as xgb

FEATURES = 28
SEED = 42


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cuda_sync() -> None:
    """Synchronize the GPU so stage timings are wall-clock complete."""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass


def device_report() -> dict:
    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "xgboost": xgb.__version__,
        "xgboost_build": xgb.build_info(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["torch_cuda_runtime"] = torch.version.cuda
        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["device_name"] = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            info["device_capability"] = f"{props.major}.{props.minor}"
            info["device_total_mem_gb"] = round(props.total_memory / 2**30, 2)
            info["torch_cuda_arch_list"] = torch.cuda.get_arch_list()
    except Exception as exc:  # pragma: no cover - informational only
        info["torch_error"] = repr(exc)
    return info


class Stage:
    """Context manager recording synchronized stage wall-clock time."""

    def __init__(self, timings: dict, name: str):
        self.timings = timings
        self.name = name

    def __enter__(self):
        cuda_sync()
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        cuda_sync()
        self.timings[self.name] = round(time.perf_counter() - self.t0, 4)
        return False


def load_matrix(path: str, name: str) -> np.ndarray:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"missing {name}: {path}")
    arr = np.load(path)
    arr = np.ascontiguousarray(arr, dtype=np.float32)
    return arr


def check_features(arr: np.ndarray, name: str, feats: int = FEATURES) -> None:
    if arr.ndim != 2 or arr.shape[1] != feats:
        raise ValueError(f"{name}: expected (n,{feats}), got {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name}: contains non-finite values")


# --------------------------------------------------------------------------- #
# train
# --------------------------------------------------------------------------- #
def train_params(args) -> dict:
    return {
        "objective": "binary:logistic",
        "tree_method": "hist",
        "device": args.device,
        "max_depth": args.max_depth,
        "eta": args.eta,
        "min_child_weight": args.min_child_weight,
        "subsample": args.subsample,
        "colsample_bytree": args.colsample_bytree,
        "reg_lambda": args.reg_lambda,
        "reg_alpha": args.reg_alpha,
        "gamma": args.gamma,
        "max_bin": args.max_bin,
        "eval_metric": "auc",
        "seed": args.seed,
        "base_score": 0.5,
    }


def cmd_train(args) -> int:
    timings: dict = {}
    t_start = time.perf_counter()
    os.makedirs(args.output, exist_ok=True)

    with Stage(timings, "load_data"):
        x_train = load_matrix(os.path.join(args.input, "train_features.npy"), "train_features")
        y_train = np.load(os.path.join(args.input, "train_labels.npy"))
        y_train = np.ascontiguousarray(y_train).astype(np.float32).ravel()
        x_val = load_matrix(os.path.join(args.input, "validation_features.npy"), "validation_features")
        check_features(x_train, "train_features")
        check_features(x_val, "validation_features")
        if x_train.shape[0] != y_train.shape[0]:
            raise ValueError("train features/labels row mismatch")
        if not np.isin(np.unique(y_train), [0.0, 1.0]).all():
            raise ValueError("train labels must be 0/1")
        input_files = {
            "train_features.npy": os.path.join(args.input, "train_features.npy"),
            "train_labels.npy": os.path.join(args.input, "train_labels.npy"),
            "validation_features.npy": os.path.join(args.input, "validation_features.npy"),
        }
        input_hashes = {name: sha256_file(p) for name, p in input_files.items()}
        source_manifest = None
        mpath = os.path.join(args.input, "manifest.json")
        if os.path.isfile(mpath):
            with open(mpath) as fh:
                source_manifest = json.load(fh)

    params = train_params(args)
    print(f"[train] rows={x_train.shape[0]} features={x_train.shape[1]} "
          f"pos={int(y_train.sum())} params={json.dumps(params)}", flush=True)

    # -- stage 1: early-stopping search on an internal split of the training
    #    rows (no validation labels are involved) ------------------------- #
    n_search_val = min(args.search_val_rows, max(1, x_train.shape[0] // 10))
    rng = np.random.default_rng(args.seed)
    perm = rng.permutation(x_train.shape[0])
    val_idx = perm[:n_search_val]
    fit_idx = perm[n_search_val:]
    dtrain_search = xgb.QuantileDMatrix(
        x_train[fit_idx], label=y_train[fit_idx],
        max_bin=params["max_bin"], nthread=args.nthread)
    dvalid_search = xgb.QuantileDMatrix(
        x_train[val_idx], label=y_train[val_idx],
        max_bin=params["max_bin"], nthread=args.nthread, ref=dtrain_search)

    best_score = float("nan")
    best_iteration = 0
    try:
        with Stage(timings, "search_train"):
            search_bst = xgb.train(
                params, dtrain_search, num_boost_round=args.search_rounds,
                evals=[(dvalid_search, "internal_val")],
                early_stopping_rounds=args.early_stopping_rounds,
                verbose_eval=args.verbose_eval)
        best_score = float(search_bst.best_score)
        best_iteration = int(search_bst.best_iteration)
    except xgb.core.XGBoostError as exc:
        print(f"[train] early-stopping search failed ({exc}); "
              f"falling back to {args.rounds} rounds", flush=True)
    del dtrain_search, dvalid_search, search_bst
    n_rounds = max(args.min_rounds, best_iteration + 1)
    print(f"[train] internal-val AUC={best_score:.5f} best_iteration={best_iteration} "
          f"-> final rounds={n_rounds}", flush=True)

    # -- stage 2: final model on all training rows ---------------------- #
    dtrain = xgb.QuantileDMatrix(
        x_train, label=y_train, max_bin=params["max_bin"], nthread=args.nthread)
    with Stage(timings, "final_train"):
        bst = xgb.train(params, dtrain, num_boost_round=n_rounds,
                        evals=[(dtrain, "train")] if args.verbose_eval else [],
                        verbose_eval=args.verbose_eval)
    num_trees = int(bst.num_boosted_rounds())

    # -- GPU inference on the validation features (evidence of GPU path) - #
    dval_gpu = xgb.QuantileDMatrix(
        x_val, max_bin=params["max_bin"], nthread=args.nthread, ref=dtrain)
    with Stage(timings, "gpu_predict"):
        preds_gpu = np.asarray(
            bst.predict(dval_gpu, iteration_range=(0, num_trees)), dtype=np.float64)
    del dval_gpu, dtrain

    # -- persist a reload-friendly model ---------------------------------- #
    # The JSON model format stores only the learned model, not the runtime
    # device, so any later reload defaults to CPU prediction.  Move this
    # in-memory booster to CPU first for the reload comparison below.
    bst.set_param({"device": "cpu"})
    model_path = os.path.join(args.output, "model.json")
    with Stage(timings, "save_model"):
        bst.save_model(model_path)
    del bst

    # -- reload through the standard API and re-predict on CPU ----------- #
    with Stage(timings, "reload_cpu_predict"):
        reloaded = xgb.Booster()
        reloaded.load_model(model_path)
        preds_cpu = np.asarray(
            reloaded.predict(xgb.DMatrix(x_val, nthread=args.nthread)),
            dtype=np.float64)
    preds_cpu = np.clip(preds_cpu, 0.0, 1.0).astype(np.float32)
    if not np.isfinite(preds_cpu).all():
        raise ValueError("non-finite predictions produced")

    pred_path = os.path.join(args.output, "validation_predictions.npy")
    with Stage(timings, "save_predictions"):
        np.save(pred_path, preds_cpu)

    max_diff = float(np.max(np.abs(preds_gpu - preds_cpu.astype(np.float64))))
    print(f"[train] validation predictions saved: {pred_path} "
          f"shape={preds_cpu.shape} min={preds_cpu.min():.6f} max={preds_cpu.max():.6f} "
          f"mean={preds_cpu.mean():.6f} | max|gpu-cpu|={max_diff:.3e}", flush=True)

    timings["total"] = round(time.perf_counter() - t_start, 4)
    manifest = {
        "task": "GPUv1-E03",
        "artifact": "higgs_event_classifier",
        "scale": "debug_real_100k_train_10k_validation",
        "source": (source_manifest or {}).get("source"),
        "source_dataset": "UCI HIGGS",
        "train_source_rows": (source_manifest or {}).get("train_source_rows"),
        "validation_source_rows": (source_manifest or {}).get("validation_source_rows"),
        "formal_source_split": False,
        "input_files": {k: os.path.basename(v) for k, v in input_files.items()},
        "input_sha256": input_hashes,
        "input_manifest_sha256": sha256_file(mpath) if os.path.isfile(mpath) else None,
        "train_rows": int(x_train.shape[0]),
        "features": int(x_train.shape[1]),
        "label_positive_count": int(y_train.sum()),
        "label_negative_count": int(x_train.shape[0] - y_train.sum()),
        "validation_rows": int(x_val.shape[0]),
        "validation_labels_used": False,
        "seed": args.seed,
        "training_params": params,
        "num_boost_round_final": int(n_rounds),
        "num_trees": num_trees,
        "num_boosted_rounds": num_trees,
        "search": {
            "search_rounds": args.search_rounds,
            "early_stopping_rounds": args.early_stopping_rounds,
            "internal_validation_rows": int(n_search_val),
            "internal_fit_rows": int(fit_idx.size),
            "best_iteration": best_iteration,
            "best_internal_validation_auc": best_score,
            "split": "seeded random permutation of training rows",
        },
        "model_path": model_path,
        "model_sha256": sha256_file(model_path),
        "reload_predict_device": "cpu",
        "reload_predict_device_note": ("JSON model format does not persist the runtime "
                                       "device; a reloaded Booster predicts on CPU by default"),
        "predictions_path": pred_path,
        "prediction_stats": {
            "shape": list(preds_cpu.shape),
            "dtype": "float32",
            "min": float(preds_cpu.min()),
            "max": float(preds_cpu.max()),
            "mean": float(preds_cpu.mean()),
            "all_finite": bool(np.isfinite(preds_cpu).all()),
            "within_unit_interval": bool(((preds_cpu >= 0) & (preds_cpu <= 1)).all()),
            "max_abs_diff_gpu_vs_cpu": max_diff,
        },
        "stage_seconds": timings,
        "device": {
            **device_report(),
            "training_device": args.device,
            "tree_method": "hist",
        },
        "commands": {
            "train": "python solution/main.py train --input input --output output",
            "predict": ("python solution/main.py predict --model output/model.json "
                        "--features input/validation_features.npy "
                        "--output output/validation_predictions.npy"),
        },
    }
    manifest_path = os.path.join(args.output, "training_manifest.json")
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=False)
    print(f"[train] wrote {manifest_path} (total {timings['total']}s)", flush=True)
    return 0


# --------------------------------------------------------------------------- #
# predict
# --------------------------------------------------------------------------- #
def cmd_predict(args) -> int:
    if not os.path.isfile(args.model):
        raise FileNotFoundError(args.model)
    x = load_matrix(args.features, "features")
    check_features(x, "features", feats=FEATURES)

    bst = xgb.Booster()
    bst.load_model(args.model)
    bst.set_param({"device": "cpu", "nthread": args.nthread})
    t0 = time.perf_counter()
    preds = np.asarray(bst.predict(xgb.DMatrix(x, nthread=args.nthread)), dtype=np.float64)
    cpu_seconds = time.perf_counter() - t0
    preds = np.clip(preds, 0.0, 1.0).astype(np.float32)
    if preds.shape != (x.shape[0],):
        preds = preds.reshape(-1)
    if preds.shape[0] != x.shape[0] or not np.isfinite(preds).all():
        raise ValueError(f"invalid predictions: shape={preds.shape} finite={np.isfinite(preds).all()}")

    parent = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(parent, exist_ok=True)
    np.save(args.output, preds)
    print(f"[predict] rows={preds.shape[0]} min={preds.min():.6f} max={preds.max():.6f} "
          f"mean={preds.mean():.6f} -> {args.output} ({cpu_seconds:.3f}s on CPU)", flush=True)
    return 0


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("train", help="train on input/, write model + predictions")
    t.add_argument("--input", default="input")
    t.add_argument("--output", default="output")
    t.add_argument("--device", default="cuda:0")
    t.add_argument("--rounds", type=int, default=400, help="fallback number of rounds")
    t.add_argument("--min-rounds", type=int, default=64,
                   help="lower bound for the number of final boosting rounds")
    t.add_argument("--search-rounds", type=int, default=1200)
    t.add_argument("--early-stopping-rounds", type=int, default=50)
    t.add_argument("--search-val-rows", type=int, default=10000)
    t.add_argument("--max-depth", type=int, default=7)
    t.add_argument("--eta", type=float, default=0.06)
    t.add_argument("--min-child-weight", type=float, default=5.0)
    t.add_argument("--subsample", type=float, default=0.9)
    t.add_argument("--colsample-bytree", type=float, default=0.8)
    t.add_argument("--reg-lambda", type=float, default=1.0)
    t.add_argument("--reg-alpha", type=float, default=0.0)
    t.add_argument("--gamma", type=float, default=0.0)
    t.add_argument("--max-bin", type=int, default=256)
    t.add_argument("--nthread", type=int, default=0)
    t.add_argument("--seed", type=int, default=SEED)
    t.add_argument("--verbose-eval", type=int, default=0)
    t.set_defaults(func=cmd_train)

    q = sub.add_parser("predict", help="reload model.json and score features")
    q.add_argument("--model", required=True)
    q.add_argument("--features", required=True)
    q.add_argument("--output", required=True)
    q.add_argument("--nthread", type=int, default=0)
    q.set_defaults(func=cmd_predict)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
