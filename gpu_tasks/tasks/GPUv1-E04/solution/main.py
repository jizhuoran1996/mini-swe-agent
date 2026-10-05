#!/usr/bin/env python3
"""GPUv1-E04 (debug variant): train a reloadable NYC taxi fare regression
estimator with XGBoost on CUDA.

Subcommands
  doctor  --input DIR                        : inspect inputs/deps, exit 0 or 78
  train   --input DIR --output DIR           : fit + validation + persist artefacts
  predict --model P --input NPY --output NPY : reload and score new rows

The training path requires a working CUDA xgboost build and will raise if
CUDA is unavailable.  CPU fallback is not permitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

TASK_ID = "GPUv1-E04"
VARIANT = "debug"

REQUIRED_INPUTS = [
    "train_features.npy",
    "train_targets.npy",
    "validation_features.npy",
]
HASHED_INPUTS = REQUIRED_INPUTS + ["manifest.json"]

# Frozen training configuration (single required run; no search).
CONFIG = {
    "n_estimators": 300,
    "max_depth": 8,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 1.0,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "tree_method": "hist",
    "device": "cuda",
    "seed": 42,
}


# ------------------------------------------------------------------------ utils
class UnavailableError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _import_numpy():
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover
        raise UnavailableError(f"numpy import failed: {exc!r}") from exc
    return np


def _import_xgb():
    try:
        import xgboost as xgb
    except Exception as exc:  # pragma: no cover
        raise UnavailableError(f"xgboost import failed: {exc!r}") from exc
    return xgb


def _make_dmatrix(xgb, X, label=None):
    """Construct a DMatrix without relying on a `device=` kwarg.

    Different xgboost builds (including the one in this container) do not
    accept a `device` argument to DMatrix.__init__.  Device placement is
    controlled through the booster parameters (device=cuda), and xgboost 3.x
    moves the hist data onto the GPU itself when trained with device=cuda.
    """
    if label is None:
        return xgb.DMatrix(X)
    return xgb.DMatrix(X, label=label)


def cuda_probe(xgb) -> dict:
    """Fail unless a CUDA-enabled xgboost build plus a live GPU is present."""
    info = {}
    try:
        info = dict(xgb.build_info())
    except Exception:
        info = {}
    if not bool(info.get("USE_CUDA", False)):
        raise UnavailableError(
            "xgboost build does not include CUDA (build_info USE_CUDA is false)"
        )
    try:
        import torch
    except Exception:
        return info
    if not torch.cuda.is_available():
        raise UnavailableError("torch reports cuda.is_available() == False")
    return info


def gpu_sync() -> bool:
    try:
        import torch
    except Exception:
        return False
    try:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            return True
    except Exception:
        return False
    return False


def environment_info(xgb) -> dict:
    env = {"python": sys.version.split()[0], "xgboost": getattr(xgb, "__version__", "?")}
    try:
        env["xgboost_build"] = {k: v for k, v in dict(xgb.build_info()).items()}
    except Exception:
        pass
    try:
        import numpy as np

        env["numpy"] = np.__version__
    except Exception:
        pass
    try:
        import torch

        env["torch"] = torch.__version__
        if torch.cuda.is_available():
            env["cuda_device"] = torch.cuda.get_device_name(0)
            env["cuda_runtime"] = torch.version.cuda
    except Exception:
        pass
    return env


def ensure_cuda_working(xgb, np) -> None:
    """Run a single tiny boosting round on the GPU to prove CUDA is usable.

    Capability check only; produces a throw-away booster.  Labels are
    provided so any default eval callback has a matching label vector.
    """
    cuda_probe(xgb)
    X = np.zeros((4, 3), dtype=np.float32)
    y = np.zeros((4,), dtype=np.float32)
    dmat = _make_dmatrix(xgb, X, label=y)
    params = {
        "tree_method": "hist",
        "device": "cuda",
        "max_depth": 1,
        "objective": "reg:squarederror",
    }
    xgb.train(params, dmat, num_boost_round=1)


# ------------------------------------------------------------------------ doctor
def cmd_doctor(args) -> int:
    problems: list[str] = []
    in_dir = Path(args.input)

    for name in REQUIRED_INPUTS + ["manifest.json"]:
        p = in_dir / name
        if not p.is_file():
            problems.append(f"missing input file: {name}")

    # Verify hashes against the manifest when available.
    man_path = in_dir / "manifest.json"
    expected: dict = {}
    if man_path.is_file():
        try:
            manifest = json.loads(man_path.read_text())
            if isinstance(manifest.get("files"), dict):
                expected = {
                    k: v for k, v in manifest["files"].items() if isinstance(v, str)
                }
        except Exception as exc:
            problems.append(f"manifest.json unreadable: {exc!r}")
    for name in REQUIRED_INPUTS:
        p = in_dir / name
        if not p.is_file():
            continue
        try:
            digest = sha256_file(p)
        except Exception as exc:
            problems.append(f"cannot read {name}: {exc!r}")
            continue
        if name in expected and expected[name] != digest:
            problems.append(
                f"sha256 mismatch for {name}: got {digest} expected {expected[name]}"
            )

    # Dependency checks.
    try:
        xgb = _import_xgb()
    except UnavailableError as exc:
        problems.append(str(exc))
        xgb = None
    try:
        _import_numpy()
    except UnavailableError as exc:
        problems.append(str(exc))

    if xgb is not None:
        try:
            cuda_probe(xgb)
        except UnavailableError as exc:
            problems.append(str(exc))

    report = {
        "task_id": TASK_ID,
        "variant": VARIANT,
        "input_dir": str(in_dir.resolve()) if in_dir.exists() else str(in_dir),
        "checked_files": REQUIRED_INPUTS + ["manifest.json"],
        "problems": problems,
        "status": "available" if not problems else "unavailable",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not problems else 78


# ------------------------------------------------------------------------- train
def cmd_train(args) -> int:
    np = _import_numpy()
    xgb = _import_xgb()
    in_dir = Path(args.input)
    out_dir = Path(args.output)

    missing = [n for n in REQUIRED_INPUTS if not (in_dir / n).is_file()]
    if missing:
        print(json.dumps({"status": "missing_inputs", "missing": missing}, indent=2))
        return 78

    # Hard requirement: real CUDA work, no CPU fallback.
    ensure_cuda_working(xgb, np)

    out_dir.mkdir(parents=True, exist_ok=True)

    input_binding = {}
    for name in HASHED_INPUTS:
        p = in_dir / name
        if p.is_file():
            input_binding[name] = sha256_file(p)

    X_tr = np.load(in_dir / "train_features.npy")
    y_tr = np.load(in_dir / "train_targets.npy").astype(np.float32)
    X_va = np.load(in_dir / "validation_features.npy")

    if X_tr.ndim != 2 or X_va.ndim != 2:
        raise ValueError(f"features must be 2-D, got {X_tr.shape} and {X_va.shape}")
    if X_tr.shape[1] != X_va.shape[1]:
        raise ValueError("train/validation feature width mismatch")
    if y_tr.shape[0] != X_tr.shape[0]:
        raise ValueError("target count does not match train feature rows")

    X_tr = np.ascontiguousarray(X_tr, dtype=np.float32)
    X_va = np.ascontiguousarray(X_va, dtype=np.float32)

    # Validation targets are optional and used only for reporting/metrics.
    val_targets_path = in_dir / "validation_targets.npy"
    y_va = None
    if val_targets_path.is_file():
        y_va = np.load(val_targets_path).astype(np.float32)
        if y_va.shape[0] != X_va.shape[0]:
            raise ValueError("validation target count does not match validation rows")

    total_start = time.perf_counter()

    gpu_sync()
    t0 = time.perf_counter()
    dtrain = _make_dmatrix(xgb, X_tr, label=y_tr)
    # The validation DMatrix must always carry labels so that xgboost's
    # default evaluation callback can compute `rmse` on it; without labels
    # (or without an eval set at all) eval_set would fail with a size
    # mismatch.  If targets are unavailable we simply train without an
    # eval set.
    dvalid = _make_dmatrix(xgb, X_va, label=y_va) if y_va is not None else None
    gpu_sync()
    t1 = time.perf_counter()

    params = {
        "objective": CONFIG["objective"],
        "eval_metric": CONFIG["eval_metric"],
        "tree_method": CONFIG["tree_method"],
        "device": CONFIG["device"],
        "max_depth": CONFIG["max_depth"],
        "eta": CONFIG["learning_rate"],
        "subsample": CONFIG["subsample"],
        "colsample_bytree": CONFIG["colsample_bytree"],
        "min_child_weight": CONFIG["min_child_weight"],
        "lambda": CONFIG["reg_lambda"],
        "seed": CONFIG["seed"],
    }

    evals = [(dvalid, "validation")] if dvalid is not None else []
    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=CONFIG["n_estimators"],
        evals=evals,
        verbose_eval=False,
    )
    gpu_sync()
    t2 = time.perf_counter()

    # Predict on a label-free DMatrix so the shape is exactly (n_rows,).
    dpred = _make_dmatrix(xgb, X_va)
    val_pred = np.asarray(booster.predict(dpred), dtype=np.float32)
    gpu_sync()
    t3 = time.perf_counter()

    if val_pred.shape != (X_va.shape[0],):
        raise RuntimeError(f"unexpected prediction shape {val_pred.shape}")

    # Metrics on the held-out validation block (debug scale: report only).
    metrics = {}
    if y_va is not None:
        y64 = y_va.astype(np.float64)
        resid = val_pred.astype(np.float64) - y64
        metrics["validation_rmse"] = float(np.sqrt(np.mean(resid ** 2)))
        metrics["validation_mae"] = float(np.mean(np.abs(resid)))
        baseline = np.full_like(y64, float(np.mean(y_tr)), dtype=np.float64)
        metrics["baseline_rmse_mean"] = float(np.sqrt(np.mean((baseline - y64) ** 2)))
        metrics["rows"] = int(y64.shape[0])
    else:
        metrics["validation_rmse"] = None
        metrics["baseline_rmse_mean"] = None
        metrics["rows"] = int(X_va.shape[0])
    metrics["baseline_mean_target"] = float(np.mean(y_tr))

    model_path = out_dir / "model.json"
    booster.save_model(str(model_path))
    np.save(out_dir / "validation_predictions.npy", val_pred.astype(np.float32))

    total_end = time.perf_counter()

    run = {
        "task_id": TASK_ID,
        "variant": VARIANT,
        "subcommand": "train",
        "input_dir": str(in_dir.resolve()),
        "input_binding": input_binding,
        "config": CONFIG,
        "environment": environment_info(xgb),
        "shapes": {
            "train_features": list(X_tr.shape),
            "train_targets": list(y_tr.shape),
            "validation_features": list(X_va.shape),
        },
        "timing_s": {
            "dmatrix_upload": t1 - t0,
            "boosting_fit": t2 - t1,
            "validation_predict": t3 - t2,
            "work_total": t3 - t1,
            "wall_total": total_end - total_start,
        },
        "gpu_synchronized": True,
        "eval_set_used": bool(evals),
        "metrics": metrics,
        "outputs": {
            "model": "model.json",
            "validation_predictions": "validation_predictions.npy",
        },
        "notes": (
            "debug-scale ordered split (50k train / 5k validation); quality "
            "figures are informational and not an admission result."
        ),
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True))

    print(
        json.dumps(
            {"status": "ok", "model": str(model_path), "metrics": metrics},
            indent=2,
        )
    )
    return 0


# ----------------------------------------------------------------------- predict
def cmd_predict(args) -> int:
    np = _import_numpy()
    xgb = _import_xgb()
    cuda_probe(xgb)

    model_path = Path(args.model)
    inp_path = Path(args.input)
    out_path = Path(args.output)

    missing = [str(p) for p in (model_path, inp_path) if not p.is_file()]
    if missing:
        print(json.dumps({"status": "missing_inputs", "missing": missing}, indent=2))
        return 78

    booster = xgb.Booster()
    booster.load_model(str(model_path))

    X = np.load(inp_path)
    if X.ndim != 2:
        raise ValueError(f"prediction input must be 2-D, got {X.shape}")
    X = np.ascontiguousarray(X, dtype=np.float32)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    gpu_sync()
    t0 = time.perf_counter()
    dmat = _make_dmatrix(xgb, X)
    preds = np.asarray(booster.predict(dmat), dtype=np.float32)
    gpu_sync()
    t1 = time.perf_counter()

    np.save(out_path, preds)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": int(preds.shape[0]),
                "output": str(out_path),
                "predict_s": t1 - t0,
            },
            indent=2,
        )
    )
    return 0


# -------------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-E04 debug taxi fare regression (XGBoost/CUDA)",
    )
    sub = p.add_subparsers(dest="command")

    d = sub.add_parser("doctor", help="inspect required inputs and dependencies")
    d.add_argument("--input", required=True, help="input directory")
    d.set_defaults(func=cmd_doctor)

    t = sub.add_parser("train", help="train and persist the fare model")
    t.add_argument("--input", required=True, help="input directory")
    t.add_argument("--output", required=True, help="output directory")
    t.set_defaults(func=cmd_train)

    pr = sub.add_parser("predict", help="reload model and score new features")
    pr.add_argument("--model", required=True, help="path to model.json")
    pr.add_argument("--input", required=True, help="path to features .npy")
    pr.add_argument("--output", required=True, help="path to write predictions .npy")
    pr.set_defaults(func=cmd_predict)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return int(args.func(args))
    except UnavailableError as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}, indent=2))
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
