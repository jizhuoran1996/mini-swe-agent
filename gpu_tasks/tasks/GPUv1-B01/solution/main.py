#!/usr/bin/env python3
"""GPUv1-B01 (debug variant) - fine-tune torchvision ResNet-50 (ImageNet-pretrained)

on a REAL CIFAR-10 subset (1000 train / 100 validation images), uint8 NHWC 32x32x3,
resized to 224 with ImageNet mean/std, 10-class head, CUDA cross-entropy.

Subcommands
-----------
train    --input DIR --output DIR    fine-tune, write checkpoint.pt,
                                    validation_predictions.npy, run.json
predict  --checkpoint P --input N.npy --output P.npy
doctor   --input DIR                 inspect required inputs/deps (no training),
                                    exit 78 if anything is missing, 0 otherwise

`main.py --help` never imports torch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

TASK_ID = "GPUv1-B01"
CLASSES = 10
RESIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
MODEL_JSON = "/models/torchvision/resnet50.json"
REQUIRED_INPUTS = ("train_images.npy", "validation_images.npy",
                   "train_labels.npy", "manifest.json")
WEIGHT_EXTS = (".pth", ".pt", ".bin", ".safetensors", ".ckpt", ".tar")


# --------------------------------------------------------------------------- io

def _sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def _resolve_weights(meta_path=MODEL_JSON):
    """Locate a local pretrained ResNet-50 checkpoint referenced by MODEL_JSON."""
    cands = []
    base = os.path.dirname(os.path.abspath(meta_path))
    if os.path.isfile(meta_path):
        try:
            meta = json.loads(Path(meta_path).read_text())
        except Exception:
            meta = None
        strings = []

        def walk(o):
            if isinstance(o, str):
                strings.append(o)
            elif isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(meta)
        for s in strings:
            if s.lower().endswith(WEIGHT_EXTS):
                cands.append(s)
                cands.append(os.path.join(base, s))
    if base and os.path.isdir(base):
        try:
            for n in sorted(os.listdir(base)):
                if n.lower().endswith(WEIGHT_EXTS):
                    cands.append(os.path.join(base, n))
        except OSError:
            pass
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def _load_state_dict(path):
    import torch
    if path.endswith(".safetensors"):
        try:
            from safetensors.torch import load_file
        except Exception:
            return None
        return dict(load_file(path))
    if path.endswith(".npz"):
        return {k: torch.from_numpy(v) for k, v in np.load(path).items()}
    obj = torch.load(path, map_location="cpu", weights_only=False)
    for _ in range(5):
        if isinstance(obj, dict):
            nxt = None
            for k in ("state_dict", "model_state_dict", "model", "module",
                      "weights", "params", "net"):
                if k in obj and isinstance(obj[k], dict) and obj[k]:
                    nxt = obj[k]
                    break
            if nxt is None:
                break
            obj = nxt
        else:
            break
    if not isinstance(obj, dict):
        return None
    out = {}
    for k, v in obj.items():
        if not hasattr(v, "shape"):
            continue
        kk = k
        changed = True
        while changed:
            changed = False
            for pre in ("module.", "model.", "backbone.", "net.", "resnet."):
                if kk.startswith(pre) and len(kk) > len(pre):
                    kk = kk[len(pre):]
                    changed = True
                    break
        out[kk] = v
    return out


# ------------------------------------------------------------------------ model

def _require_cuda():
    import torch
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required for this task but torch.cuda.is_available() is False")
    return torch.device("cuda")


def _build_model(device):
    """ResNet-50 with a fresh 10-class head, initialised from real ImageNet weights."""
    import torch
    import torchvision as tv

    model = tv.models.resnet50(weights=None)
    in_f = model.fc.in_features
    model.fc = torch.nn.Linear(in_f, CLASSES)
    own = model.state_dict()
    source = None

    wpath = _resolve_weights()
    if wpath:
        sd = _load_state_dict(wpath)
        filt = {}
        if sd:
            for k, v in sd.items():
                if k in ("fc.weight", "fc.bias"):
                    continue
                if k in own and tuple(v.shape) == tuple(own[k].shape):
                    filt[k] = v
        if len(filt) >= 100:
            model.load_state_dict(filt, strict=False)
            source = {"kind": "local_checkpoint", "path": wpath, "tensors_loaded": len(filt)}

    if source is None:
        try:
            ref = tv.models.resnet50(weights=tv.models.ResNet50_Weights.IMAGENET1K_V2)
        except Exception as exc:
            raise SystemExit(
                "no usable pretrained ResNet-50 weights found (looked at %s and the "
                "torchvision hub cache); refusing to train from random init: %s"
                % (MODEL_JSON, exc))
        rsd = ref.state_dict()
        filt = {k: v for k, v in rsd.items()
                if k in own and k not in ("fc.weight", "fc.bias")
                and tuple(v.shape) == tuple(own[k].shape)}
        model.load_state_dict(filt, strict=False)
        source = {"kind": "torchvision_imagenet1k_v2", "tensors_loaded": len(filt)}

    model.to(device)
    return model, source


def _model_from_checkpoint(ckpt, device):
    import torch
    import torchvision as tv
    model = tv.models.resnet50(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, int(ckpt.get("num_classes", CLASSES)))
    model.load_state_dict(ckpt["state_dict"])
    model.to(device)
    model.eval()
    return model


def _preprocess_batch(imgs, device):
    """uint8 NHWC (N,H,W,3) -> normalised float32 NCHW (N,3,224,224) on device."""
    import torch
    import torch.nn.functional as F

    x = torch.from_numpy(np.ascontiguousarray(imgs)).to(device)
    if x.dtype == torch.uint8:
        x = x.float().div_(255.0)
    else:
        x = x.float()
        if float(x.max()) > 1.5:
            x = x.div_(255.0)
    if x.dim() == 3:
        x = x.unsqueeze(0)
    if x.dim() != 4:
        raise ValueError(f"expected 3D/4D image array, got {tuple(x.shape)}")
    if x.shape[-1] == 3 and x.shape[1] != 3:
        x = x.permute(0, 3, 1, 2)
    x = x.contiguous()
    if x.shape[1] != 3:
        raise ValueError(f"expected 3 channels, got {x.shape[1]}")
    if tuple(x.shape[-2:]) != (RESIZE, RESIZE):
        x = F.interpolate(x, size=(RESIZE, RESIZE), mode="bilinear",
                          align_corners=False, antialias=True)
    mean = torch.tensor(IMAGENET_MEAN, device=device, dtype=x.dtype).view(1, 3, 1, 1)
    std = torch.tensor(IMAGENET_STD, device=device, dtype=x.dtype).view(1, 3, 1, 1)
    return (x - mean) / std


# ------------------------------------------------------------------------ train

def cmd_train(args):
    import torch

    t_start = time.perf_counter()
    device = _require_cuda()
    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in ("train_images.npy", "validation_images.npy", "train_labels.npy"):
        if not (in_dir / name).is_file():
            raise SystemExit(f"missing required input: {in_dir / name}")

    seed = int(args.seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    train_imgs = np.load(in_dir / "train_images.npy")
    val_imgs = np.load(in_dir / "validation_images.npy")
    train_labels = np.load(in_dir / "train_labels.npy").astype(np.int64).reshape(-1)
    n_train = int(train_imgs.shape[0])
    n_val = int(val_imgs.shape[0])
    if train_labels.shape[0] != n_train:
        raise SystemExit(f"train_labels {train_labels.shape[0]} != train_images {n_train}")
    if train_labels.min() < 0 or train_labels.max() >= CLASSES:
        raise SystemExit("train labels outside [0,10)")

    model, init_source = _build_model(device)
    for p in model.parameters():
        p.requires_grad_(False)
    for p in model.fc.parameters():
        p.requires_grad_(True)
    # Frozen backbone: keep BatchNorm running statistics fixed.
    model.eval()

    fc_w0 = model.fc.weight.detach().clone()
    fc_b0 = model.fc.bias.detach().clone()

    opt = torch.optim.Adam(model.fc.parameters(), lr=float(args.lr))
    crit = torch.nn.CrossEntropyLoss()

    bs = int(args.batch_size)
    epochs = int(args.epochs)
    gen = torch.Generator().manual_seed(seed)
    seen = np.zeros(n_train, dtype=bool)
    losses = []
    grad_norms = []
    step = 0

    torch.cuda.synchronize()
    t_train0 = time.perf_counter()
    for _ep in range(epochs):
        order = torch.randperm(n_train, generator=gen).numpy()
        for i in range(0, n_train, bs):
            idx = order[i:i + bs]
            xb = _preprocess_batch(train_imgs[idx], device)
            yb = torch.from_numpy(train_labels[idx]).to(device)
            opt.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = crit(logits, yb)
            loss.backward()
            gn = float(torch.nn.utils.clip_grad_norm_(model.fc.parameters(), 1e9))
            opt.step()
            step += 1
            losses.append(float(loss.detach()))
            grad_norms.append(gn)
            seen[idx] = True
            del xb, yb, logits, loss
    torch.cuda.synchronize()
    train_wall = time.perf_counter() - t_train0

    # ---- validation inference (softmax only; labels are held by the evaluator)
    model.eval()
    torch.cuda.synchronize()
    t_val0 = time.perf_counter()
    chunks = []
    with torch.no_grad():
        for i in range(0, n_val, bs):
            xb = _preprocess_batch(val_imgs[i:i + bs], device)
            chunks.append(torch.softmax(model(xb), dim=1).float().cpu())
    torch.cuda.synchronize()
    val_wall = time.perf_counter() - t_val0
    val_probs = (torch.cat(chunks, 0).numpy().astype(np.float32) if chunks
                 else np.zeros((0, CLASSES), dtype=np.float32))

    head_dw = float((model.fc.weight.detach() - fc_w0).abs().max())
    head_db = float((model.fc.bias.detach() - fc_b0).abs().max())

    ckpt = {
        "format": "gpuv1-b01-checkpoint-v1",
        "task_id": TASK_ID,
        "variant": "debug_only",
        "model": "torchvision/resnet50",
        "num_classes": CLASSES,
        "state_dict": model.state_dict(),
        "optimizer_state_dict": opt.state_dict(),
        "optimizer_name": "adam",
        "lr": float(args.lr),
        "step": step,
        "global_step": step,
        "epochs": epochs,
        "batch_size": bs,
        "seed": seed,
        "input_size": RESIZE,
        "mean": list(IMAGENET_MEAN),
        "std": list(IMAGENET_STD),
        "pretrained_init": init_source,
        "train_indices_seen": np.nonzero(seen)[0].astype(np.int64).tolist(),
        "rng": {
            "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all(),
            "numpy": np.random.get_state(),
            "python": random.getstate(),
        },
    }
    torch.save(ckpt, out_dir / "checkpoint.pt")
    np.save(out_dir / "validation_predictions.npy", val_probs)

    run = {
        "task_id": TASK_ID,
        "variant": "debug_only",
        "formal_large_claimed": False,
        "device": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "pretrained_init": init_source,
        "config": {
            "seed": seed, "epochs": epochs, "batch_size": bs, "lr": float(args.lr),
            "optimizer": "adam", "loss": "cross_entropy", "frozen_backbone": True,
            "trainable_params": ["fc.weight", "fc.bias"],
            "input_size": RESIZE, "mean": list(IMAGENET_MEAN), "std": list(IMAGENET_STD),
        },
        "data": {
            "train_samples": n_train,
            "validation_samples": n_val,
            "classes": CLASSES,
            "train_images_shape": list(train_imgs.shape),
            "train_images_dtype": str(train_imgs.dtype),
            "validation_images_shape": list(val_imgs.shape),
        },
        "training": {
            "steps": step,
            "loss_first": losses[0] if losses else None,
            "loss_last": losses[-1] if losses else None,
            "loss_mean": float(np.mean(losses)) if losses else None,
            "grad_norm_last": grad_norms[-1] if grad_norms else None,
            "head_updated": bool(head_dw > 0.0 or head_db > 0.0),
            "head_weight_max_abs_delta": head_dw,
            "head_bias_max_abs_delta": head_db,
        },
        "coverage": {
            "train_indices_seen": int(seen.sum()),
            "train_indices_total": n_train,
            "all_train_images_used": bool(seen.all()),
        },
        "timings_s": {
            "train_wall_s": train_wall,
            "validation_inference_wall_s": val_wall,
            "total_wall_s": time.perf_counter() - t_start,
        },
        "outputs": {
            "checkpoint": "checkpoint.pt",
            "validation_predictions": "validation_predictions.npy",
            "run_json": "run.json",
        },
        "validation_predictions_shape": list(val_probs.shape),
        "notes": (
            "Debug-scale run: real CIFAR-10 subset (1000 train / 100 val) fine-tuning an "
            "ImageNet-pretrained ResNet-50 with a new 10-class head on CUDA. This is NOT a "
            "completed ImageNet-1K training run; the reference-large spec is not claimed. "
            "Validation accuracy is intentionally not reported here because the labels are "
            "held by the independent evaluator."
        ),
    }
    with open(out_dir / "run.json", "w") as fh:
        json.dump(run, fh, indent=2)

    print(json.dumps({
        "steps": step,
        "train_loss_last": run["training"]["loss_last"],
        "coverage_all_seen": run["coverage"]["all_train_images_used"],
        "head_updated": run["training"]["head_updated"],
        "train_wall_s": round(train_wall, 3),
        "output_dir": str(out_dir),
    }, indent=2))
    return 0


# ---------------------------------------------------------------------- predict

def cmd_predict(args):
    import torch

    device = _require_cuda()
    ckpt_path = Path(args.checkpoint)
    in_path = Path(args.input)
    out_path = Path(args.output)
    if not ckpt_path.is_file():
        raise SystemExit(f"checkpoint not found: {ckpt_path}")
    if not in_path.is_file():
        raise SystemExit(f"input array not found: {in_path}")

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    if not isinstance(ckpt, dict) or "state_dict" not in ckpt:
        raise SystemExit("checkpoint does not contain a 'state_dict'")
    model = _model_from_checkpoint(ckpt, device)

    imgs = np.load(in_path)
    bs = int(args.batch_size)
    chunks = []
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        for i in range(0, int(imgs.shape[0]), bs):
            xb = _preprocess_batch(imgs[i:i + bs], device)
            chunks.append(torch.softmax(model(xb), dim=1).float().cpu())
    torch.cuda.synchronize()
    wall = time.perf_counter() - t0

    probs = (torch.cat(chunks, 0).numpy().astype(np.float32) if chunks
             else np.zeros((0, CLASSES), dtype=np.float32))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, probs)
    print(json.dumps({
        "checkpoint": str(ckpt_path),
        "input": str(in_path),
        "input_shape": list(imgs.shape),
        "output": str(out_path),
        "output_shape": list(probs.shape),
        "inference_wall_s": round(wall, 4),
    }, indent=2))
    return 0


# ----------------------------------------------------------------------- doctor

def cmd_doctor(args):
    ok, missing = [], []
    in_dir = Path(args.input)
    if not in_dir.is_dir():
        missing.append(f"input directory does not exist: {in_dir}")
    else:
        ok.append(f"input directory: {in_dir}")

    manifest = None
    mp = in_dir / "manifest.json"
    if mp.is_file():
        try:
            manifest = json.loads(mp.read_text())
            ok.append(f"manifest.json parsed ({TASK_ID if manifest.get('task_id') is None else manifest.get('task_id')})")
        except Exception as exc:
            missing.append(f"manifest.json unreadable: {exc}")

    for name in REQUIRED_INPUTS:
        p = in_dir / name
        if not p.is_file():
            missing.append(f"missing required input file: {p}")
            continue
        if not name.endswith(".npy"):
            continue
        try:
            a = np.load(p, mmap_mode="r")
            ok.append(f"{name}: shape={tuple(a.shape)} dtype={a.dtype}")
        except Exception as exc:
            missing.append(f"{p} not loadable: {exc}")

    if (in_dir / "train_images.npy").is_file() and (in_dir / "train_labels.npy").is_file():
        try:
            n_i = np.load(in_dir / "train_images.npy", mmap_mode="r").shape[0]
            n_l = np.load(in_dir / "train_labels.npy", mmap_mode="r").reshape(-1).shape[0]
            if n_i != n_l:
                missing.append(f"train_images/train_labels count mismatch: {n_i} vs {n_l}")
            else:
                ok.append(f"train images/labels aligned ({n_i} samples)")
        except Exception:
            pass

    if manifest and isinstance(manifest.get("files"), dict):
        for name, digest in manifest["files"].items():
            p = in_dir / name
            if not p.is_file():
                missing.append(f"manifest lists a file that is absent: {p}")
                continue
            try:
                actual = _sha256(p)
            except OSError as exc:
                missing.append(f"cannot hash {p}: {exc}")
                continue
            if actual != digest:
                missing.append(f"sha256 mismatch for {p}: got {actual}, expected {digest}")
            else:
                ok.append(f"sha256 ok: {name}")

    torch = None
    try:
        import torch as _torch
        torch = _torch
        ok.append(f"torch {torch.__version__} importable")
    except Exception as exc:
        missing.append(f"torch unavailable: {exc}")
    try:
        import torchvision as _tv
        ok.append(f"torchvision {_tv.__version__} importable")
    except Exception as exc:
        missing.append(f"torchvision unavailable: {exc}")

    if torch is not None:
        if torch.cuda.is_available():
            ok.append(f"CUDA available: {torch.cuda.get_device_name(0)} (torch {torch.version.cuda})")
        else:
            missing.append("CUDA is not available; this task requires a GPU")

    wpath = _resolve_weights()
    if wpath:
        ok.append(f"pretrained weights resolved: {wpath}")
    else:
        hub = os.path.join(os.path.expanduser("~"), ".cache", "torch", "hub", "checkpoints")
        cached = [n for n in (os.listdir(hub) if os.path.isdir(hub) else []) if "resnet50" in n]
        if cached:
            ok.append(f"pretrained weights via torch hub cache: {cached}")
        else:
            missing.append(
                f"no local pretrained ResNet-50 checkpoint resolvable from {MODEL_JSON} "
                f"(and no resnet50* file in {hub})")

    print(json.dumps({"status": "ok" if not missing else "missing",
                      "available": ok, "missing": missing}, indent=2))
    return 0 if not missing else 78


# ------------------------------------------------------------------------- main

def build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-B01 (debug): fine-tune an ImageNet-pretrained torchvision "
                    "ResNet-50 on a real CIFAR-10 1000/100 subset (uint8 NHWC 32x32x3).")
    sub = p.add_subparsers(dest="cmd")

    t = sub.add_parser("train", help="fine-tune and write checkpoint/predictions/run.json")
    t.add_argument("--input", required=True, help="input directory")
    t.add_argument("--output", required=True, help="output directory")
    t.add_argument("--epochs", type=int, default=10)
    t.add_argument("--batch-size", type=int, default=50)
    t.add_argument("--lr", type=float, default=1e-3)
    t.add_argument("--seed", type=int, default=1234)
    t.set_defaults(func=cmd_train)

    q = sub.add_parser("predict", help="run the reloaded checkpoint on a new .npy batch")
    q.add_argument("--checkpoint", required=True)
    q.add_argument("--input", required=True, help=".npy of uint8 NHWC images")
    q.add_argument("--output", required=True, help="destination .npy of softmax (N,10)")
    q.add_argument("--batch-size", type=int, default=50)
    q.set_defaults(func=cmd_predict)

    d = sub.add_parser("doctor", help="inspect inputs/deps without training")
    d.add_argument("--input", required=True)
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
