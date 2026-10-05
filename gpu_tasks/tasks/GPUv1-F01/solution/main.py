#!/usr/bin/env python3
"""GPUv1-F01 (debug variant): train a re-loadable 4-parameter cosmological
regressor from real CosmoFlow v2 128^3 x 4 density volumes on a real CUDA GPU.

Commands
--------
  python solution/main.py --help
  python solution/main.py doctor  --input input
  python solution/main.py train   --input input --output output
  python solution/main.py predict --checkpoint output/checkpoint.pt \
                                  --input NEW_FIELDS.npy --output preds.npy

The entry point does not import torch/numpy at module import time, so
``--help`` never loads models or touches CUDA.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time

TASK_ID = "GPUv1-F01"
VARIANT = "debug_only"
REQUIRED_INPUT_FILES = (
    "train_fields.npy",
    "train_targets.npy",
    "validation_fields.npy",
    "manifest.json",
)
EXIT_MISSING = 78
EXIT_FAIL = 1
MIN_UPDATES = 5

PREPROCESSING = {
    "step1": "x = log1p(max(count, 0))",
    "step2": (
        "x = x / mean(x), mean taken per sample over all voxels and all four "
        "channel; divisor is 1.0 when the per-sample mean is 0"
    ),
    "dtype_after": "float32",
}


# --------------------------------------------------------------------------- #
# shared helpers (stdlib only at import time)
# --------------------------------------------------------------------------- #
def _sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _collect_hashes(obj, out: dict) -> None:
    """Best-effort extraction of {filename: sha256} pairs from a manifest."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "files" and isinstance(value, dict):
                for name, meta in value.items():
                    digest = None
                    if isinstance(meta, str) and len(meta) == 64:
                        digest = meta
                    elif isinstance(meta, dict):
                        for hk in ("sha256", "sha256sum", "hash", "digest"):
                            cand = meta.get(hk)
                            if isinstance(cand, str) and len(cand) == 64:
                                digest = cand
                                break
                    if digest:
                        out[os.path.basename(str(name))] = digest.lower()
            else:
                _collect_hashes(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_hashes(item, out)


def _safe_cudnn_version(torch) -> int | None:
    """Return the cuDNN version, or None if it cannot be queried.

    PyTorch raises RuntimeError from torch.backends.cudnn.version() when the
    runtime cuDNN shipped in LD_LIBRARY_PATH does not match the version the
    wheel was compiled against. That mismatch must not abort training, so the
    call is always guarded.
    """
    try:
        if not torch.backends.cudnn.is_available():
            return None
        return int(torch.backends.cudnn.version())
    except Exception:
        return None


def _disable_cudnn_if_broken(torch) -> dict:
    """Probe cuDNN and disable the backend if the runtime is unusable.

    Disabling cuDNN keeps all computation on the CUDA device (generic CUDA
    kernels for conv3d), so the task still performs real GPU work. It only
    avoids a hard crash caused by an incompatible system cuDNN build.
    """
    info = {"cudnn_available": False, "cudnn_version": None, "cudnn_disabled": False}
    try:
        if not torch.backends.cudnn.is_available():
            return info
        info["cudnn_available"] = True
        try:
            info["cudnn_version"] = int(torch.backends.cudnn.version())
        except Exception as exc:  # version probe itself can raise
            torch.backends.cudnn.enabled = False
            info["cudnn_disabled"] = True
            info["cudnn_error"] = f"{type(exc).__name__}: {exc}"
        return info
    except Exception as exc:
        info["cudnn_error"] = f"{type(exc).__name__}: {exc}"
        try:
            torch.backends.cudnn.enabled = False
            info["cudnn_disabled"] = True
        except Exception:
            pass
        return info


def _canonical_fields(arr, name: str):
    """Normalise a volume stack to (N, D, H, W, C) with C == 4.

    Returns (canonical_array, layout_tag).  The canonical array may be a view
    or a transposed copy of the input; it is never modified in place.
    """
    import numpy as np

    if arr.ndim == 5:
        if arr.shape[-1] == 4:
            return arr, "NDHWC"
        if arr.shape[1] == 4:
            return np.ascontiguousarray(np.transpose(arr, (0, 2, 3, 4, 1))), "NCDHW"
        raise ValueError(
            f"{name}: expected a 4-channel volume stack, got shape {tuple(arr.shape)}"
        )
    if arr.ndim == 4:
        if arr.shape[-1] == 4:
            return arr[None, ...], "DHWC"
        if arr.shape[0] == 4:
            return np.ascontiguousarray(np.transpose(arr, (1, 2, 3, 0)))[None, ...], "CDHW"
        raise ValueError(
            f"{name}: expected a single 4-channel volume, got shape {tuple(arr.shape)}"
        )
    raise ValueError(f"{name}: expected 4D/5D volume data, got shape {tuple(arr.shape)}")


def _preprocess(canonical):
    """log1p(max(x,0)) then per-sample mean normalisation. Returns (x, means)."""
    import numpy as np

    x = np.asarray(canonical).astype(np.float32, copy=True)
    np.maximum(x, 0.0, out=x)
    np.log1p(x, out=x)
    flat = x.reshape(x.shape[0], -1)
    means = flat.mean(axis=1)
    means = np.where(np.isfinite(means) & (means > 0.0), means, 1.0).astype(np.float32)
    x /= means.reshape(-1, *([1] * (x.ndim - 1)))
    return x, means


def _to_nchw_tensor(batch_np, device):
    """(b, D, H, W, C) float32 numpy -> contiguous (b, C, D, H, W) CUDA tensor."""
    import numpy as np
    import torch

    contiguous = np.ascontiguousarray(np.transpose(batch_np, (0, 4, 1, 2, 3)))
    return torch.from_numpy(contiguous).to(device, non_blocking=False)


# --------------------------------------------------------------------------- #
# model
# --------------------------------------------------------------------------- #
_MODEL_CLASS = None


def get_model_class():
    """Build (once) the 3D CNN class.  torch is imported lazily."""
    global _MODEL_CLASS
    if _MODEL_CLASS is not None:
        return _MODEL_CLASS

    import torch
    import torch.nn as nn

    class Cosmo3DCNN(nn.Module):
        """Strided 3D conv encoder over all four redshift channels + linear head."""

        def __init__(self, in_channels: int = 4, out_dim: int = 4, width: int = 16,
                     clamp: bool = True):
            super().__init__()
            self.in_channels = int(in_channels)
            self.out_dim = int(out_dim)
            self.width = int(width)
            self.clamp = bool(clamp)
            w = self.width

            def block(ci, co):
                return nn.Sequential(
                    nn.Conv3d(ci, co, kernel_size=3, stride=2, padding=1, bias=False),
                    nn.BatchNorm3d(co),
                    nn.ReLU(inplace=True),
                )

            self.encoder = nn.Sequential(
                block(self.in_channels, w),
                block(w, 2 * w),
                block(2 * w, 2 * w),
                block(2 * w, 4 * w),
                block(4 * w, 4 * w),
            )
            self.pool = nn.AdaptiveAvgPool3d(1)
            self.head = nn.Linear(4 * w, self.out_dim)

        def forward(self, x):
            x = self.encoder(x)
            x = self.pool(x).flatten(1)
            x = self.head(x)
            if self.clamp:
                x = torch.tanh(x)
            return x

        def config(self):
            return {
                "arch": "Cosmo3DCNN",
                "in_channels": self.in_channels,
                "out_dim": self.out_dim,
                "width": self.width,
                "clamp": self.clamp,
                "encoder": "5 x [Conv3d(k=3,s=2,p=1,bias=False) + BatchNorm3d + ReLU] "
                           "channels [w, 2w, 2w, 4w, 4w]",
                "pool": "AdaptiveAvgPool3d(1)",
                "head": f"Linear({4 * self.width}, {self.out_dim})",
                "output_activation": "tanh" if self.clamp else "identity",
            }

    _MODEL_CLASS = Cosmo3DCNN
    return _MODEL_CLASS


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def cmd_doctor(args) -> int:
    inp = os.path.abspath(args.input)
    report = {
        "task_id": TASK_ID,
        "variant": VARIANT,
        "command": "doctor",
        "input_dir": inp,
        "dependencies": {},
        "files": {},
        "expected_sha256": {},
        "missing": [],
        "warnings": [],
        "ok": False,
    }

    np = None
    try:
        import numpy as _np
        np = _np
        report["dependencies"]["numpy"] = _np.__version__
    except Exception as exc:  # pragma: no cover
        report["dependencies"]["numpy"] = None
        report["missing"].append(f"python package 'numpy' unavailable: {exc}")

    torch = None
    try:
        import torch as _torch
        torch = _torch
        report["dependencies"]["torch"] = _torch.__version__
        report["dependencies"]["torch_cuda_build"] = _torch.version.cuda
        report["dependencies"]["python"] = sys.version.split()[0]
        info = _disable_cudnn_if_broken(_torch)
        report["dependencies"]["cudnn"] = info.get("cudnn_version")
        report["dependencies"]["cudnn_disabled"] = info.get("cudnn_disabled", False)
        if info.get("cudnn_error"):
            report["warnings"].append(
                "cuDNN probe failed (" + info["cudnn_error"] + "); "
                "torch.backends.cudnn.enabled set to False, generic CUDA kernels "
                "will be used instead"
            )
        cuda_ok = bool(_torch.cuda.is_available())
        report["dependencies"]["cuda_available"] = cuda_ok
        report["dependencies"]["cuda_device_count"] = (
            _torch.cuda.device_count() if cuda_ok else 0
        )
        if cuda_ok:
            prop = _torch.cuda.get_device_properties(0)
            report["dependencies"]["cuda_device_name"] = prop.name
            report["dependencies"]["cuda_capability"] = f"{prop.major}.{prop.minor}"
            report["dependencies"]["cuda_device_memory_gib"] = round(
                prop.total_memory / float(2 ** 30), 2
            )
        else:
            report["missing"].append(
                "CUDA device not available; this task requires real GPU compute "
                "(torch.cuda.is_available() is False)"
            )
    except Exception as exc:  # pragma: no cover
        report["dependencies"]["torch"] = None
        report["missing"].append(f"python package 'torch' unavailable: {exc}")

    if not os.path.isdir(inp):
        report["missing"].append(f"input directory not found: {inp}")
        _print_report(report)
        return EXIT_MISSING

    manifest_path = os.path.join(inp, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                _collect_hashes(json.load(fh), report["expected_sha256"])
        except Exception as exc:
            report["warnings"].append(f"manifest.json could not be parsed: {exc}")

    for name in REQUIRED_INPUT_FILES:
        path = os.path.join(inp, name)
        entry = {"path": path, "exists": os.path.isfile(path)}
        if not entry["exists"]:
            report["missing"].append(f"missing required input file: {name}")
            report["files"][name] = entry
            continue
        size = os.path.getsize(path)
        entry["bytes"] = size
        if size == 0:
            report["missing"].append(f"input file is empty: {name}")
        entry["sha256"] = _sha256(path)
        expected = report["expected_sha256"].get(name)
        if expected:
            entry["sha256_matches_manifest"] = (expected == entry["sha256"])
            if expected != entry["sha256"]:
                report["missing"].append(
                    f"sha256 mismatch for {name}: got {entry['sha256']}, manifest says {expected}"
                )
        if name.endswith(".npy") and np is not None and size > 0:
            try:
                arr = np.load(path, mmap_mode="r")
                entry["dtype"] = str(arr.dtype)
                entry["shape"] = [int(s) for s in arr.shape]
                del arr
            except Exception as exc:
                report["missing"].append(f"cannot read npy header of {name}: {exc}")
        report["files"][name] = entry

    tf = report["files"].get("train_fields.npy", {})
    tt = report["files"].get("train_targets.npy", {})
    vf = report["files"].get("validation_fields.npy", {})
    if "shape" in tf:
        shape = tf["shape"]
        if len(shape) != 5 or 4 not in (shape[-1], shape[1]):
            report["missing"].append(
                f"train_fields.npy shape {shape} is not a stack of 4-channel 3D volumes"
            )
        elif tf.get("dtype") not in ("int16", "int32", "int64", "uint16", "float32"):
            report["warnings"].append(f"train_fields dtype {tf.get('dtype')} is unusual")
    if "shape" in tt:
        shape = tt["shape"]
        if len(shape) != 2 or shape[-1] != 4:
            report["missing"].append(
                f"train_targets.npy shape {shape} is not (N, 4)"
            )
        if "shape" in tf and tf["shape"][0] != shape[0]:
            report["missing"].append(
                f"train_fields.npy has {tf['shape'][0]} samples but train_targets.npy has {shape[0]}"
            )
    if "shape" in vf:
        shape = vf["shape"]
        if len(shape) != 5 or 4 not in (shape[-1], shape[1]):
            report["missing"].append(
                f"validation_fields.npy shape {shape} is not a stack of 4-channel 3D volumes"
            )

    report["missing"] = sorted(set(report["missing"]))
    report["ok"] = not report["missing"]
    _print_report(report)
    return 0 if report["ok"] else EXIT_MISSING


def _print_report(report: dict) -> None:
    print(json.dumps(report, indent=2, sort_keys=False))


# --------------------------------------------------------------------------- #
# train
# --------------------------------------------------------------------------- #
def cmd_train(args) -> int:
    t_start = time.perf_counter()
    import numpy as np
    import torch

    inp = os.path.abspath(args.input)
    out = os.path.abspath(args.output)
    os.makedirs(out, exist_ok=True)

    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError(
            "real CUDA compute is required for training, but "
            "torch.cuda.is_available() is False"
        )
    device = torch.device(args.device)
    if device.type != "cuda":
        raise RuntimeError(f"training device must be a CUDA device, got {device}")

    cudnn_info = _disable_cudnn_if_broken(torch)

    seed = int(args.seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    paths = {
        "train_fields.npy": os.path.join(inp, "train_fields.npy"),
        "train_targets.npy": os.path.join(inp, "train_targets.npy"),
        "validation_fields.npy": os.path.join(inp, "validation_fields.npy"),
    }
    for name, path in paths.items():
        if not os.path.isfile(path):
            raise FileNotFoundError(f"missing required input file: {path}")

    input_meta = {}
    for name, path in paths.items():
        input_meta[name] = {
            "path": path,
            "bytes": os.path.getsize(path),
            "sha256": _sha256(path),
        }

    train_arr = np.load(paths["train_fields.npy"])
    targets = np.load(paths["train_targets.npy"])
    val_arr = np.load(paths["validation_fields.npy"])

    train_can, train_layout = _canonical_fields(train_arr, "train_fields.npy")
    val_can, val_layout = _canonical_fields(val_arr, "validation_fields.npy")
    input_meta["train_fields.npy"].update(shape=list(train_arr.shape), dtype=str(train_arr.dtype),
                                          layout=train_layout)
    input_meta["train_targets.npy"].update(shape=list(targets.shape), dtype=str(targets.dtype))
    input_meta["validation_fields.npy"].update(shape=list(val_arr.shape), dtype=str(val_arr.dtype),
                                               layout=val_layout)

    targets = np.asarray(targets, dtype=np.float32)
    if targets.ndim == 1:
        targets = targets.reshape(1, -1)
    if targets.ndim != 2 or targets.shape[1] != 4:
        raise ValueError(f"train_targets.npy must have shape (N, 4), got {targets.shape}")
    if targets.shape[0] != train_can.shape[0]:
        raise ValueError(
            f"train_targets.npy has {targets.shape[0]} rows but train_fields.npy has "
            f"{train_can.shape[0]} volumes"
        )
    if not np.all(np.isfinite(targets)):
        raise ValueError("train_targets.npy contains non-finite values")

    fields, field_means = _preprocess(train_can)
    val_fields, val_means = _preprocess(val_can)
    del train_arr, val_arr, train_can, val_can

    n_samples = int(fields.shape[0])
    batch_size = max(1, min(int(args.batch_size), n_samples))
    steps_per_epoch = int(math.ceil(n_samples / batch_size))
    epochs = max(int(args.epochs), int(math.ceil(MIN_UPDATES / steps_per_epoch)))
    clamp = bool(
        float(targets.min()) >= -1.0 - 1e-6 and float(targets.max()) <= 1.0 + 1e-6
    )

    ModelCls = get_model_class()
    model = ModelCls(in_channels=int(fields.shape[-1]), out_dim=4,
                     width=int(args.width), clamp=clamp).to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=float(args.lr))
    loss_fn = torch.nn.functional.mse_loss

    rng = np.random.default_rng(seed)
    covered = np.zeros(n_samples, dtype=bool)
    loss_curve = []
    param_count = sum(p.numel() for p in model.parameters())
    h2d_bytes = 0
    step = 0

    model.train()
    ev0 = torch.cuda.Event(enable_timing=True)
    ev1 = torch.cuda.Event(enable_timing=True)
    t_train0 = time.perf_counter()
    torch.cuda.synchronize()
    ev0.record()
    for _epoch in range(epochs):
        order = rng.permutation(n_samples)
        for start in range(0, n_samples, batch_size):
            idx = order[start:start + batch_size]
            covered[idx] = True
            batch_np = fields[idx]
            x = _to_nchw_tensor(batch_np, device)
            y = torch.from_numpy(np.ascontiguousarray(targets[idx])).to(device)
            h2d_bytes += int(batch_np.size * batch_np.dtype.itemsize)
            pred = model(x)
            loss = loss_fn(pred, y)
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            optimiser.step()
            step += 1
            loss_curve.append(float(loss.detach().to("cpu").item()))
    ev1.record()
    torch.cuda.synchronize()
    gpu_train_s = ev0.elapsed_time(ev1) / 1000.0
    wall_train_s = time.perf_counter() - t_train0

    if step < MIN_UPDATES:
        raise RuntimeError(f"only {step} optimizer updates performed, need >= {MIN_UPDATES}")
    if not bool(covered.all()):
        raise RuntimeError(
            f"not all training samples were used: {int(covered.sum())}/{n_samples} covered"
        )

    model.eval()
    with torch.no_grad():
        train_pred_chunks = []
        for start in range(0, n_samples, batch_size):
            stop = min(start + batch_size, n_samples)
            x = _to_nchw_tensor(fields[start:stop], device)
            train_pred_chunks.append(model(x).to("cpu").numpy())
        train_preds = np.concatenate(train_pred_chunks, axis=0).astype(np.float32)

        val_pred_chunks = []
        for start in range(0, val_fields.shape[0], batch_size):
            stop = min(start + batch_size, val_fields.shape[0])
            x = _to_nchw_tensor(val_fields[start:stop], device)
            val_pred_chunks.append(model(x).to("cpu").numpy())
        val_preds = np.concatenate(val_pred_chunks, axis=0).astype(np.float32)

    residual = train_preds - targets
    per_param_mae = np.abs(residual).mean(axis=0)
    per_param_mse = (residual ** 2).mean(axis=0)
    train_mse = float((residual ** 2).mean())

    checkpoint_path = os.path.join(out, "checkpoint.pt")
    checkpoint = {
        "format_version": 1,
        "task_id": TASK_ID,
        "variant": VARIANT,
        "model_config": model.config(),
        "model_state_dict": {k: v.detach().to("cpu") for k, v in model.state_dict().items()},
        "optimizer_config": {"name": "Adam", "lr": float(args.lr)},
        "optimizer_state_dict": optimiser.state_dict(),
        "step": int(step),
        "epochs": int(epochs),
        "samples": int(n_samples),
        "seed": seed,
        "rng_state": {
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "torch_cpu": torch.get_rng_state(),
            "torch_cuda_all": torch.cuda.get_rng_state_all(),
        },
        "preprocessing": PREPROCESSING,
        "target_stats": {
            "min": targets.min(axis=0).tolist(),
            "max": targets.max(axis=0).tolist(),
            "mean": targets.mean(axis=0).tolist(),
            "std": targets.std(axis=0).tolist(),
        },
        "input_sha256": {k: v["sha256"] for k, v in input_meta.items()},
    }
    torch.save(checkpoint, checkpoint_path)

    validation_path = os.path.join(out, "validation_predictions.npy")
    np.save(validation_path, val_preds)
    validation_csv = os.path.join(out, "validation_predictions.csv")
    with open(validation_csv, "w", encoding="utf-8") as fh:
        fh.write("volume_index,param_0,param_1,param_2,param_3\n")
        for row_i, row in enumerate(val_preds):
            fh.write(str(row_i) + "," + ",".join(f"{float(v):.9g}" for v in row) + "\n")

    peak_alloc = torch.cuda.max_memory_allocated() / float(2 ** 30)
    peak_reserved = torch.cuda.max_memory_reserved() / float(2 ** 30)
    total_wall_s = time.perf_counter() - t_start

    run = {
        "task_id": TASK_ID,
        "variant": VARIANT,
        "command": "train",
        "status": "ok",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device": {
            "type": device.type,
            "index": device.index,
            "name": torch.cuda.get_device_name(device),
            "capability": f"{torch.cuda.get_device_capability(device)[0]}."
                          f"{torch.cuda.get_device_capability(device)[1]}",
        },
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "torch_cuda_build": torch.version.cuda,
            "numpy": np.__version__,
            "cudnn": _safe_cudnn_version(torch),
            "cudnn_disabled": bool(cudnn_info.get("cudnn_disabled")),
        },
        "inputs": {"dir": inp, "files": input_meta},
        "config": {
            "seed": seed,
            "epochs": int(epochs),
            "requested_epochs": int(args.epochs),
            "batch_size": batch_size,
            "steps_per_epoch": steps_per_epoch,
            "lr": float(args.lr),
            "width": int(args.width),
            "optimizer": "Adam",
            "loss": "MSE(mean over batch and 4 params)",
            "optimizer_updates": int(step),
            "min_required_updates": MIN_UPDATES,
            "model_params": int(param_count),
            "preprocessing": PREPROCESSING,
            "output_clamped_to_unit_interval": clamp,
            "output_activation": "tanh" if clamp else "identity",
            "clamp_note": (
                "all source targets lie in [-1,1]: tanh output used, predictions clamped"
                if clamp else
                "source targets leave [-1,1]: outputs are NOT clamped, limitation recorded here"
            ),
            "normalisation_note": (
                "targets are used in the provided normalised units; no de-normalisation "
                "constants are shipped with the debug bundle"
            ),
        },
        "source_labels": {
            "train_targets_sha256": input_meta["train_targets.npy"]["sha256"],
            "target_stats": {
                "min": targets.min(axis=0).tolist(),
                "max": targets.max(axis=0).tolist(),
                "mean": targets.mean(axis=0).tolist(),
                "std": targets.std(axis=0).tolist(),
            },
            "validation_targets_available": False,
        },
        "training": {
            "updates": int(step),
            "epochs_run": int(epochs),
            "samples": int(n_samples),
            "samples_covered": int(covered.sum()),
            "all_samples_covered": bool(covered.all()),
            "first_loss": loss_curve[0],
            "last_loss": loss_curve[-1],
            "loss_curve": loss_curve,
            "final_train_mse": train_mse,
            "final_train_mae_per_param": per_param_mae.tolist(),
            "final_train_mse_per_param": per_param_mse.tolist(),
            "final_train_predictions": train_preds.tolist(),
            "final_train_targets": targets.tolist(),
        },
        "timings": {
            "wall_train_s": wall_train_s,
            "gpu_event_train_s": gpu_train_s,
            "total_wall_s": total_wall_s,
            "timing_method": "torch.cuda.Event + torch.cuda.synchronize + time.perf_counter",
        },
        "memory": {
            "peak_allocated_gib": peak_alloc,
            "peak_reserved_gib": peak_reserved,
            "h2d_input_bytes": int(h2d_bytes),
        },
        "preprocessing_means": {
            "train_volume_means": field_means.tolist(),
            "validation_volume_means": val_means.tolist(),
        },
        "outputs": {
            "checkpoint": checkpoint_path,
            "validation_predictions": validation_path,
            "validation_predictions_csv": validation_csv,
            "run_json": os.path.join(out, "run.json"),
            "metrics_json": os.path.join(out, "metrics.json"),
        },
        "validation_predictions": {
            "shape": list(val_preds.shape),
            "min": val_preds.min(axis=0).tolist(),
            "max": val_preds.max(axis=0).tolist(),
            "mean": val_preds.mean(axis=0).tolist(),
            "values": val_preds.tolist(),
        },
        "notes": [
            "debug-only variant: four genuine train volumes and two genuine "
            "validation volumes from the CosmoFlow v2 mini shards",
            "PyTorch 3D CNN replaces the distributed TensorFlow CosmoFlow model; "
            "no claim of MLPerf-quality accuracy",
            "every optimizer update is a real CUDA forward/backward/step on source labels",
            "cuDNN is probed defensively: if the system runtime cuDNN mismatches the "
            "wheel build, torch.backends.cudnn.enabled is set to False and generic "
            "CUDA kernels are used instead of crashing",
        ],
    }
    with open(os.path.join(out, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=2)

    metrics = {
        "task_id": TASK_ID,
        "variant": VARIANT,
        "updates": int(step),
        "all_samples_covered": bool(covered.all()),
        "samples": int(n_samples),
        "final_train_mse": train_mse,
        "final_train_mae_per_param": per_param_mae.tolist(),
        "last_loss": loss_curve[-1],
        "first_loss": loss_curve[0],
        "input_sha256": {k: v["sha256"] for k, v in input_meta.items()},
        "config": run["config"],
        "validation_predictions_shape": list(val_preds.shape),
        "wall_train_s": wall_train_s,
        "gpu_event_train_s": gpu_train_s,
        "validation_labels_available": False,
        "cudnn_disabled": bool(cudnn_info.get("cudnn_disabled")),
        "note": "validation MSE cannot be computed: the two source validation volumes "
                "have no labels in this debug bundle",
    }
    with open(os.path.join(out, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    print(json.dumps({
        "status": "ok",
        "command": "train",
        "updates": int(step),
        "epochs": int(epochs),
        "all_samples_covered": bool(covered.all()),
        "first_loss": loss_curve[0],
        "last_loss": loss_curve[-1],
        "final_train_mse": train_mse,
        "final_train_mae_per_param": per_param_mae.tolist(),
        "validation_predictions": val_preds.tolist(),
        "wall_train_s": wall_train_s,
        "gpu_event_train_s": gpu_train_s,
        "outputs": run["outputs"],
    }, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# predict
# --------------------------------------------------------------------------- #
def cmd_predict(args) -> int:
    import numpy as np
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError(
            "real CUDA compute is required for inference, but "
            "torch.cuda.is_available() is False"
        )
    device = torch.device(args.device)
    if device.type != "cuda":
        raise RuntimeError(f"predict device must be a CUDA device, got {device}")

    # Same defensive cuDNN handling as training; without this an incompatible
    # system cuDNN can abort any convolution on the CUDA device.
    cudnn_info = _disable_cudnn_if_broken(torch)

    checkpoint_path = os.path.abspath(args.checkpoint)
    if not os.path.isfile(checkpoint_path):
        raise FileNotFoundError(f"checkpoint not found: {checkpoint_path}")
    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"input volume file not found: {input_path}")
    out_arg = os.path.abspath(args.output)
    if os.path.isdir(out_arg):
        output_path = os.path.join(out_arg, "predictions.npy")
    elif out_arg.endswith(".npy"):
        output_path = out_arg
    else:
        output_path = out_arg + ".npy"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    config = checkpoint.get("model_config")
    if not isinstance(config, dict):
        raise ValueError("checkpoint does not contain a usable model_config")
    ModelCls = get_model_class()
    model = ModelCls(
        in_channels=int(config.get("in_channels", 4)),
        out_dim=int(config.get("out_dim", 4)),
        width=int(config.get("width", 16)),
        clamp=bool(config.get("clamp", True)),
    ).to(device)
    state = checkpoint.get("model_state_dict")
    if not isinstance(state, dict):
        raise ValueError("checkpoint does not contain model_state_dict")
    model.load_state_dict(state)
    model.eval()

    arr = np.load(input_path)
    canonical, layout = _canonical_fields(arr, os.path.basename(input_path))
    fields, means = _preprocess(canonical)
    del arr

    batch_size = max(1, int(args.batch_size))
    ev0 = torch.cuda.Event(enable_timing=True)
    ev1 = torch.cuda.Event(enable_timing=True)
    t0 = time.perf_counter()
    torch.cuda.synchronize()
    ev0.record()
    chunks = []
    with torch.no_grad():
        for start in range(0, fields.shape[0], batch_size):
            stop = min(start + batch_size, fields.shape[0])
            x = _to_nchw_tensor(fields[start:stop], device)
            chunks.append(model(x).to("cpu").numpy())
    ev1.record()
    torch.cuda.synchronize()
    gpu_s = ev0.elapsed_time(ev1) / 1000.0
    wall_s = time.perf_counter() - t0
    predictions = np.concatenate(chunks, axis=0).astype(np.float32)
    if predictions.shape[1] != 4:
        raise RuntimeError(f"unexpected prediction shape {predictions.shape}")
    np.save(output_path, predictions)

    print(json.dumps({
        "status": "ok",
        "command": "predict",
        "checkpoint": checkpoint_path,
        "input": input_path,
        "input_shape": list(fields.shape),
        "input_layout": layout,
        "output": output_path,
        "predictions_shape": list(predictions.shape),
        "predictions": predictions.tolist(),
        "input_mean_scalars": means.tolist(),
        "output_activation": config.get("output_activation"),
        "device": torch.cuda.get_device_name(device),
        "cudnn_disabled": bool(cudnn_info.get("cudnn_disabled")),
        "wall_s": wall_s,
        "gpu_event_s": gpu_s,
    }, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "GPUv1-F01 (debug variant): CUDA 3D-CNN regressor for four cosmological "
            "parameters from 128^3 x 4 density volumes"
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="{doctor,train,predict}")

    doctor = sub.add_parser(
        "doctor", help="inspect required inputs and dependencies without running the job"
    )
    doctor.add_argument("--input", default="input", help="input directory (default: input)")

    train = sub.add_parser("train", help="train the 3D CNN and write checkpoint/run.json")
    train.add_argument("--input", default="input", help="input directory (default: input)")
    train.add_argument("--output", default="output", help="output directory (default: output)")
    train.add_argument("--epochs", type=int, default=30, help="epochs (default: 30)")
    train.add_argument("--batch-size", type=int, default=2, help="batch size (default: 2)")
    train.add_argument("--lr", type=float, default=1e-3, help="Adam learning rate (default: 1e-3)")
    train.add_argument("--width", type=int, default=16, help="base channel width (default: 16)")
    train.add_argument("--seed", type=int, default=1234, help="RNG seed (default: 1234)")
    train.add_argument("--device", default="cuda:0", help="CUDA device (default: cuda:0)")

    predict = sub.add_parser("predict", help="run a saved checkpoint on new volumes")
    predict.add_argument("--checkpoint", required=True, help="path to checkpoint.pt")
    predict.add_argument("--input", required=True, help="path to a .npy volume stack")
    predict.add_argument("--output", required=True, help="output .npy path or directory")
    predict.add_argument("--batch-size", type=int, default=2, help="batch size (default: 2)")
    predict.add_argument("--device", default="cuda:0", help="CUDA device (default: cuda:0)")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        if args.command == "doctor":
            return cmd_doctor(args)
        if args.command == "train":
            return cmd_train(args)
        if args.command == "predict":
            return cmd_predict(args)
    except Exception as exc:  # noqa: BLE001 - surfaced as JSON + non-zero exit
        import traceback
        print(json.dumps({
            "status": "error",
            "command": args.command,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }, indent=2), file=sys.stderr)
        return EXIT_FAIL
    return 2


if __name__ == "__main__":
    sys.exit(main())
