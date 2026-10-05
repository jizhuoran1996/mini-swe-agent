#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPUv1-F02 (debug variant): CAM5 All-Hist extreme-weather segmentation.

Trains a small 3-level U-Net (16 input channels -> 3 classes, with skip
connections) on the frozen debug subset of the CAM5 All-Hist / TECA
event-mask data (native full-domain, stride 4 => 192x288 fields), then
predicts class masks and per-class probabilities for the two official
validation frames.

Classes: 0 background, 1 tropical_cyclone, 2 atmospheric_river.

Subcommands
-----------
  doctor  --input DIR                       verify inputs + deps (no training)
  train   --input DIR --output DIR          train, predict, save artifacts
  predict --checkpoint PATH --input NPY --output DIR

CUDA is mandatory. Every real-work command exits non-zero when
``torch.cuda.is_available()`` is False. No CPU fallback, no mock weights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

TASK_ID = "GPUv1-F02"
CLASS_NAMES = {0: "background", 1: "tropical_cyclone", 2: "atmospheric_river"}

DEFAULT_SEED = 20240601
DEFAULT_EPOCHS = 12
DEFAULT_LR = 1e-3
DEFAULT_BASE = 32

REQUIRED_INPUTS = (
    "train_fields.npy",
    "train_labels.npy",
    "validation_fields.npy",
    "manifest.json",
)
EXPECTED_TRAIN_FIELDS = (6, 16, 192, 288)
EXPECTED_TRAIN_LABELS = (6, 192, 288)
EXPECTED_VAL_FIELDS = (2, 16, 192, 288)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


_MODEL_CACHE = {}


def _model_classes():
    """Build (and cache) the torch model classes lazily.

    Importing torch only happens when a real-work command runs, so
    ``main.py --help`` stays fast and never touches the model code.
    """
    if _MODEL_CACHE:
        return _MODEL_CACHE["DoubleConv"], _MODEL_CACHE["UNet3"]

    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class DoubleConv(nn.Module):
        """(conv3x3 -> GroupNorm -> ReLU) x 2."""

        def __init__(self, cin, cout, groups=8):
            super().__init__()
            g = min(groups, cout)
            while cout % g != 0:
                g -= 1
            self.block = nn.Sequential(
                nn.Conv2d(cin, cout, 3, padding=1, bias=False),
                nn.GroupNorm(g, cout),
                nn.ReLU(inplace=True),
                nn.Conv2d(cout, cout, 3, padding=1, bias=False),
                nn.GroupNorm(g, cout),
                nn.ReLU(inplace=True),
            )

        def forward(self, x):
            return self.block(x)

    class UpBlock(nn.Module):
        """Transposed conv upsample + skip concat + double conv."""

        def __init__(self, cin, cskip, cout):
            super().__init__()
            self.up = nn.ConvTranspose2d(cin, cout, kernel_size=2, stride=2)
            self.conv = DoubleConv(cout + cskip, cout)

        def forward(self, x, skip):
            x = self.up(x)
            if x.shape[-2:] != skip.shape[-2:]:
                x = F.interpolate(x, size=skip.shape[-2:], mode="nearest")
            return self.conv(torch.cat([x, skip], dim=1))

    class UNet3(nn.Module):
        """3-level encoder/decoder U-Net with skip connections."""

        def __init__(self, in_channels=16, n_classes=3, base=32):
            super().__init__()
            self.enc1 = DoubleConv(in_channels, base)
            self.enc2 = DoubleConv(base, base * 2)
            self.enc3 = DoubleConv(base * 2, base * 4)
            self.bottleneck = DoubleConv(base * 4, base * 8)
            self.dec3 = UpBlock(base * 8, base * 4, base * 4)
            self.dec2 = UpBlock(base * 4, base * 2, base * 2)
            self.dec1 = UpBlock(base * 2, base, base)
            self.head = nn.Conv2d(base, n_classes, 1)

        def forward(self, x):
            s1 = self.enc1(x)
            s2 = self.enc2(F.max_pool2d(s1, 2))
            s3 = self.enc3(F.max_pool2d(s2, 2))
            b = self.bottleneck(F.max_pool2d(s3, 2))
            d3 = self.dec3(b, s3)
            d2 = self.dec2(d3, s2)
            d1 = self.dec1(d2, s1)
            return self.head(d1)

    _MODEL_CACHE["DoubleConv"] = DoubleConv
    _MODEL_CACHE["UNet3"] = UNet3
    return DoubleConv, UNet3


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------
def cmd_doctor(args):
    """Inspect required files & dependencies. No training / inference."""
    report = {
        "command": "doctor",
        "task_id": TASK_ID,
        "input": os.path.abspath(args.input),
        "checks": [],
        "missing": [],
        "warnings": [],
    }

    def add(name, ok, detail):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["missing"].append({"name": name, "detail": detail})

    in_dir = os.path.abspath(args.input)
    add("input_dir_exists", os.path.isdir(in_dir), in_dir)

    # ---- numpy dependency -------------------------------------------------
    try:
        import numpy as np
        report["numpy_version"] = np.__version__
        add("import_numpy", True, np.__version__)
    except Exception as exc:  # pragma: no cover
        np = None
        add("import_numpy", False, repr(exc))

    # ---- torch / CUDA dependency -----------------------------------------
    try:
        import torch
        report["torch_version"] = torch.__version__
        add("import_torch", True, torch.__version__)
        cuda_ok = bool(torch.cuda.is_available())
        add("torch_cuda_available", cuda_ok, "cuda.is_available()=%s" % cuda_ok)
        if cuda_ok:
            try:
                report["cuda_device"] = torch.cuda.get_device_name(0)
                report["cuda_capability"] = list(torch.cuda.get_device_capability(0))
            except Exception as exc:  # pragma: no cover
                report["cuda_device"] = "unknown: %r" % (exc,)
    except Exception as exc:  # pragma: no cover
        add("import_torch", False, repr(exc))
        add("torch_cuda_available", False, "torch import failed")

    # ---- required files ---------------------------------------------------
    expected_shapes = {
        "train_fields.npy": EXPECTED_TRAIN_FIELDS,
        "train_labels.npy": EXPECTED_TRAIN_LABELS,
        "validation_fields.npy": EXPECTED_VAL_FIELDS,
    }
    manifest = None
    for name in REQUIRED_INPUTS:
        path = os.path.join(in_dir, name)
        if not os.path.isfile(path):
            add("file:%s" % name, False, "missing: %s" % path)
            continue
        size = os.path.getsize(path)
        add("file:%s" % name, True, "%s (%d bytes)" % (path, size))
        if name.endswith(".npy") and np is not None:
            try:
                arr = np.load(path, mmap_mode="r")
                shape = tuple(int(v) for v in arr.shape)
                dtype = str(arr.dtype)
                exp = expected_shapes.get(name)
                ok = (exp is None) or (shape == exp)
                detail = "shape=%s dtype=%s expected=%s" % (shape, dtype, exp)
                if ok:
                    add("shape:%s" % name, True, detail)
                else:
                    add("shape:%s" % name, False, detail)
                report.setdefault("npy", {})[name] = {"shape": list(shape), "dtype": dtype}
            except Exception as exc:
                add("read:%s" % name, False, repr(exc))
        elif name == "manifest.json":
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    manifest = json.load(fh)
                add("parse:manifest.json", True, "task_id=%s" % manifest.get("task_id"))
            except Exception as exc:
                add("parse:manifest.json", False, repr(exc))

    # ---- optional sha256 cross-check against the manifest -----------------
    if manifest and np is not None:
        declared = manifest.get("files", {})
        for name, digest in declared.items():
            path = os.path.join(in_dir, name)
            if not os.path.isfile(path):
                continue
            try:
                actual = _sha256_file(path)
            except Exception as exc:  # pragma: no cover
                report["warnings"].append("sha256(%s) failed: %r" % (name, exc))
                continue
            if actual != digest:
                add("sha256:%s" % name, False, "expected=%s actual=%s" % (digest, actual))
            else:
                add("sha256:%s" % name, True, actual)

    report["available"] = len(report["missing"]) == 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["available"] else 78


# --------------------------------------------------------------------------
# train
# --------------------------------------------------------------------------
def cmd_train(args):
    import numpy as np
    import torch
    import torch.nn as nn

    started_at = _now_iso()
    t_wall0 = time.perf_counter()

    if not torch.cuda.is_available():
        sys.stderr.write(
            "ERROR: CUDA is required for GPUv1-F02 but torch.cuda.is_available() "
            "is False. Refusing to run on CPU.\n"
        )
        return 3

    device = torch.device("cuda", 0)
    torch.cuda.set_device(device)

    in_dir = os.path.abspath(args.input)
    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)

    missing = [
        n for n in ("train_fields.npy", "train_labels.npy", "validation_fields.npy")
        if not os.path.isfile(os.path.join(in_dir, n))
    ]
    if missing:
        sys.stderr.write("ERROR: missing required inputs in %s: %s\n" % (in_dir, ", ".join(missing)))
        return 2

    t_load0 = time.perf_counter()
    train_fields = np.load(os.path.join(in_dir, "train_fields.npy")).astype(np.float32)
    train_labels = np.load(os.path.join(in_dir, "train_labels.npy")).astype(np.int64)
    val_fields = np.load(os.path.join(in_dir, "validation_fields.npy")).astype(np.float32)
    t_load = time.perf_counter() - t_load0

    if train_fields.shape != EXPECTED_TRAIN_FIELDS:
        sys.stderr.write("ERROR: train_fields shape %s != %s\n" % (train_fields.shape, EXPECTED_TRAIN_FIELDS))
        return 2
    if train_labels.shape != EXPECTED_TRAIN_LABELS:
        sys.stderr.write("ERROR: train_labels shape %s != %s\n" % (train_labels.shape, EXPECTED_TRAIN_LABELS))
        return 2
    if val_fields.shape != EXPECTED_VAL_FIELDS:
        sys.stderr.write("ERROR: validation_fields shape %s != %s\n" % (val_fields.shape, EXPECTED_VAL_FIELDS))
        return 2

    n_train = int(train_fields.shape[0])
    n_val = int(val_fields.shape[0])

    # ---- per-channel normalisation from the TRAIN fields only -------------
    mean = train_fields.mean(axis=(0, 2, 3)).astype(np.float32)
    std = np.maximum(train_fields.std(axis=(0, 2, 3)).astype(np.float32), 1e-6)

    # ---- class weighting from the real training labels --------------------
    counts = np.bincount(train_labels.reshape(-1), minlength=3).astype(np.float64)
    freqs = np.maximum(counts / max(counts.sum(), 1.0), 1e-12)
    weights = np.minimum(np.power(1.0 / freqs, 0.5), 30.0)
    weights = weights / weights.mean()

    seed = int(args.seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    class_weights = torch.tensor(weights, dtype=torch.float32, device=device)

    x_all = (train_fields - mean[None, :, None, None]) / std[None, :, None, None]
    v_all = (val_fields - mean[None, :, None, None]) / std[None, :, None, None]
    X = torch.from_numpy(np.ascontiguousarray(x_all)).to(device)
    Y = torch.from_numpy(np.ascontiguousarray(train_labels)).to(device)
    V = torch.from_numpy(np.ascontiguousarray(v_all)).to(device)

    _, UNet3 = _model_classes()
    base = int(args.base)
    model = UNet3(in_channels=16, n_classes=3, base=base).to(device)
    n_params = int(sum(p.numel() for p in model.parameters()))

    optimizer = torch.optim.Adam(model.parameters(), lr=float(args.lr))
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    epochs = max(1, int(args.epochs))
    loss_history = []
    step = 0

    torch.cuda.synchronize()
    t_train0 = time.perf_counter()
    model.train()
    for _ep in range(epochs):
        for i in range(n_train):
            optimizer.zero_grad(set_to_none=True)
            logits = model(X[i:i + 1])
            loss = criterion(logits, Y[i:i + 1])
            loss.backward()
            optimizer.step()
            step += 1
            loss_history.append(round(float(loss.detach().item()), 6))
    torch.cuda.synchronize()
    t_train = time.perf_counter() - t_train0

    if step < 5:
        sys.stderr.write("ERROR: only %d updates performed, need >= 5\n" % step)
        return 4

    # ---- inference on the two official validation frames ------------------
    model.eval()
    torch.cuda.synchronize()
    t_pred0 = time.perf_counter()
    with torch.no_grad():
        val_logits = model(V)
        val_probs = torch.softmax(val_logits, dim=1)
        val_pred = torch.argmax(val_probs, dim=1)
        train_logits = model(X)
        train_pred = torch.argmax(train_logits, dim=1)
    torch.cuda.synchronize()
    t_pred = time.perf_counter() - t_pred0

    probabilities = val_probs.detach().cpu().numpy().astype(np.float32)
    predictions = val_pred.detach().cpu().numpy().astype(np.int64)
    train_pred_np = train_pred.detach().cpu().numpy()

    # ---- IoU against the REAL training labels (sanity, not headline) ------
    ious = {}
    for c in range(3):
        inter = int(((train_pred_np == c) & (train_labels == c)).sum())
        union = int(((train_pred_np == c) | (train_labels == c)).sum())
        ious[str(c)] = (float(inter) / float(union)) if union > 0 else None
    valid = [v for v in ious.values() if v is not None]
    ious["mean"] = (sum(valid) / len(valid)) if valid else None

    pred_counts = np.bincount(predictions.reshape(-1), minlength=3).astype(int).tolist()

    # ---- RNG / optimizer state -------------------------------------------
    rng_state = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "torch_cuda": torch.cuda.get_rng_state_all(),
    }

    checkpoint = {
        "task_id": TASK_ID,
        "format_version": 1,
        "config": {
            "arch": "unet3",
            "in_channels": 16,
            "n_classes": 3,
            "base": base,
            "classes": CLASS_NAMES,
        },
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "step": step,
        "epochs": epochs,
        "lr": float(args.lr),
        "seed": seed,
        "norm_mean": mean.tolist(),
        "norm_std": std.tolist(),
        "class_weights": weights.tolist(),
        "loss_history": loss_history,
        "final_loss": loss_history[-1] if loss_history else None,
        "train_iou": ious,
        "rng": rng_state,
    }

    ckpt_path = os.path.join(out_dir, "checkpoint.pt")
    torch.save(checkpoint, ckpt_path)

    pred_path = os.path.join(out_dir, "predictions.npy")
    prob_path = os.path.join(out_dir, "probabilities.npy")
    np.save(pred_path, predictions)
    np.save(prob_path, probabilities)

    # ---- reload verification (fresh module instance, real weights) --------
    _, UNet3b = _model_classes()
    reloaded = UNet3b(in_channels=16, n_classes=3, base=base).to(device)
    loaded = torch.load(ckpt_path, map_location=device, weights_only=False)
    reloaded.load_state_dict(loaded["model_state"])
    reloaded.eval()
    with torch.no_grad():
        logits_a = model(V[:1])
        logits_b = reloaded(V[:1])
    reload_max_abs_diff = float((logits_a - logits_b).abs().max().item())
    reload_ok = reload_max_abs_diff < 1e-4
    if not reload_ok:
        sys.stderr.write("ERROR: checkpoint reload mismatch (max|d|=%.3e)\n" % reload_max_abs_diff)
        return 5

    t_wall = time.perf_counter() - t_wall0
    finished_at = _now_iso()

    run = {
        "task_id": TASK_ID,
        "scale": "debug_only",
        "reference_large_claimed": False,
        "command": "train",
        "started_at": started_at,
        "finished_at": finished_at,
        "wall_seconds": t_wall,
        "timings": {
            "load_seconds": t_load,
            "train_seconds": t_train,
            "predict_seconds": t_pred,
            "wall_seconds": t_wall,
            "synchronized": True,
        },
        "device": {
            "name": torch.cuda.get_device_name(0),
            "capability": list(torch.cuda.get_device_capability(0)),
            "total_memory_bytes": int(torch.cuda.get_device_properties(0).total_memory),
        },
        "environment": {
            "torch": torch.__version__,
            "numpy": np.__version__,
            "cuda": torch.version.cuda,
            "python": sys.version.split()[0],
        },
        "inputs": {
            "dir": in_dir,
            "train_fields_shape": list(train_fields.shape),
            "train_labels_shape": list(train_labels.shape),
            "validation_fields_shape": list(val_fields.shape),
            "train_samples": n_train,
            "validation_samples": n_val,
        },
        "normalization": {
            "source": "train_fields per-channel mean/std",
            "mean": mean.tolist(),
            "std": std.tolist(),
        },
        "classes": CLASS_NAMES,
        "class_counts_train": counts.astype(int).tolist(),
        "class_weights": weights.tolist(),
        "model": {
            "arch": "unet3",
            "in_channels": 16,
            "n_classes": 3,
            "base": base,
            "parameters": n_params,
        },
        "training": {
            "optimizer": "Adam",
            "lr": float(args.lr),
            "loss": "CrossEntropyLoss(weight=class_weights)",
            "epochs": epochs,
            "updates": step,
            "batch_size": 1,
            "covers_all_train_fields": step >= n_train,
            "loss_history": loss_history,
            "final_loss": loss_history[-1] if loss_history else None,
        },
        "train_iou": ious,
        "validation_prediction_class_counts": pred_counts,
        "validation_all_background": bool(pred_counts[1] == 0 and pred_counts[2] == 0),
        "reload_check": {
            "ok": reload_ok,
            "max_abs_logit_diff": reload_max_abs_diff,
        },
        "outputs": {
            "checkpoint": ckpt_path,
            "predictions": pred_path,
            "probabilities": prob_path,
            "predictions_shape": list(predictions.shape),
            "predictions_dtype": str(predictions.dtype),
            "probabilities_shape": list(probabilities.shape),
            "probabilities_dtype": str(probabilities.dtype),
        },
        "notes": (
            "debug-only adaptation: frozen 6-train/2-validation All-Hist stride-4 subset, "
            "small 3-level U-Net instead of full DeepCAM/DeepLabV3+. "
            "Validation frames carry no labels; the hidden per-class IoU is scored separately."
        ),
    }
    run_path = os.path.join(out_dir, "run.json")
    with open(run_path, "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=2, sort_keys=True, default=str)

    summary = {
        "status": "ok",
        "checkpoint": ckpt_path,
        "predictions": pred_path,
        "probabilities": prob_path,
        "run_json": run_path,
        "updates": step,
        "final_loss": run["training"]["final_loss"],
        "train_iou": ious,
        "validation_prediction_class_counts": pred_counts,
        "reload_ok": reload_ok,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


# --------------------------------------------------------------------------
# predict
# --------------------------------------------------------------------------
def cmd_predict(args):
    import numpy as np
    import torch

    if not torch.cuda.is_available():
        sys.stderr.write(
            "ERROR: CUDA is required for GPUv1-F02 but torch.cuda.is_available() "
            "is False. Refusing to run on CPU.\n"
        )
        return 3
    if not os.path.isfile(args.checkpoint):
        sys.stderr.write("ERROR: checkpoint not found: %s\n" % args.checkpoint)
        return 2
    if not os.path.isfile(args.input):
        sys.stderr.write("ERROR: input npy not found: %s\n" % args.input)
        return 2

    t0 = time.perf_counter()
    device = torch.device("cuda", 0)
    torch.cuda.set_device(device)

    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    cfg = ckpt["config"]
    _, UNet3 = _model_classes()
    model = UNet3(cfg["in_channels"], cfg["n_classes"], cfg["base"]).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    mean = np.asarray(ckpt["norm_mean"], dtype=np.float32)
    std = np.asarray(ckpt["norm_std"], dtype=np.float32)

    arr = np.load(args.input).astype(np.float32)
    if arr.ndim == 3:
        arr = arr[None, ...]
    if arr.ndim != 4 or arr.shape[1] != mean.shape[0]:
        sys.stderr.write(
            "ERROR: input must be (N, %d, H, W) or (%d, H, W); got %s\n"
            % (mean.shape[0], mean.shape[0], tuple(arr.shape))
        )
        return 2

    x = (arr - mean[None, :, None, None]) / std[None, :, None, None]
    x_t = torch.from_numpy(np.ascontiguousarray(x)).to(device)

    torch.cuda.synchronize()
    with torch.no_grad():
        logits = model(x_t)
        probs = torch.softmax(logits, dim=1)
    torch.cuda.synchronize()
    t_infer = time.perf_counter() - t0

    predictions = probs.argmax(1).detach().cpu().numpy().astype(np.int64)
    probabilities = probs.detach().cpu().numpy().astype(np.float32)

    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)
    pred_path = os.path.join(out_dir, "predictions.npy")
    prob_path = os.path.join(out_dir, "probabilities.npy")
    np.save(pred_path, predictions)
    np.save(prob_path, probabilities)

    counts = np.bincount(predictions.reshape(-1), minlength=cfg["n_classes"]).astype(int).tolist()
    meta = {
        "task_id": TASK_ID,
        "command": "predict",
        "checkpoint": os.path.abspath(args.checkpoint),
        "input": os.path.abspath(args.input),
        "input_shape": list(arr.shape),
        "device": torch.cuda.get_device_name(0),
        "predictions": pred_path,
        "probabilities": prob_path,
        "predictions_shape": list(predictions.shape),
        "probabilities_shape": list(probabilities.shape),
        "class_counts": counts,
        "infer_seconds": t_infer,
        "checkpoint_step": int(ckpt.get("step", -1)),
    }
    with open(os.path.join(out_dir, "predict.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True, default=str)

    print(json.dumps(meta, indent=2, sort_keys=True))
    return 0


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "GPUv1-F02 (debug variant): train a 3-level U-Net segmentation model "
            "for CAM5 All-Hist extreme-weather classes "
            "(0 background / 1 tropical_cyclone / 2 atmospheric_river)."
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="{doctor,train,predict}")

    p_doctor = sub.add_parser("doctor", help="inspect required inputs and dependencies")
    p_doctor.add_argument("--input", required=True, help="input directory")
    p_doctor.set_defaults(func=cmd_doctor)

    p_train = sub.add_parser("train", help="train on CUDA and write artifacts")
    p_train.add_argument("--input", required=True, help="input directory")
    p_train.add_argument("--output", required=True, help="output directory")
    p_train.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_train.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    p_train.add_argument("--lr", type=float, default=DEFAULT_LR)
    p_train.add_argument("--base", type=int, default=DEFAULT_BASE)
    p_train.set_defaults(func=cmd_train)

    p_pred = sub.add_parser("predict", help="run a saved checkpoint on new fields")
    p_pred.add_argument("--checkpoint", required=True, help="checkpoint.pt path")
    p_pred.add_argument("--input", required=True, help="new fields .npy")
    p_pred.add_argument("--output", required=True, help="output directory")
    p_pred.set_defaults(func=cmd_predict)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) is None:
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
