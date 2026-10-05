#!/usr/bin/env python3
"""
GPUv1-B10 (debug variant, scale=debug_only)

Adapt the HuggingFace metric outdoor monocular depth model
  depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf
on the packaged VKITTI2 debug split (12 train RGB+metric-depth frames,
4 held-out frames, 392x126) using real CUDA gradient updates, then export a
standard HF checkpoint, full optimizer/step/RNG training state and metric
depth predictions (float32 metres).

Subcommands (no network, no package installation, local files only):
    main.py doctor  --input INPUT  [--output OUTPUT] [--model MODEL]
    main.py train   --input INPUT  --output OUTPUT [--model MODEL] [options]
    main.py predict --checkpoint CKPT --input validation.jsonl --output PRED.npy

`main.py --help` never imports torch/transformers and never touches a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

TASK_ID = "GPUv1-B10"
DEFAULT_MODEL = "/models/depth-anything--Depth-Anything-V2-Metric-Outdoor-Small-hf"
MODEL_REPO = "depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf"
MODEL_REVISION = "fd2c22027eaf20374204f14099b8341e1925ad39"
DEPTH_MIN = 0.1   # metres, inclusive lower bound of the valid mask
DEPTH_MAX = 80.0  # metres, exclusive upper bound (outdoor config)
MIN_STEPS = 12

# --------------------------------------------------------------------------- #
# input parsing helpers
# --------------------------------------------------------------------------- #

IMG_KEYS = ("image", "image_path", "rgb", "rgb_path", "img", "img_path", "file", "image_file")
DEP_KEYS = ("depth", "depth_path", "depth_npy", "depth_file", "target", "gt_depth", "depth_map")
PATHY_KEYS = ("path", "file", "filename", "name")


def load_jsonl(path: Path):
    recs = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"ERROR: invalid JSON at {path}:{lineno}: {exc}")
            if isinstance(obj, dict):
                recs.append(obj)
            elif isinstance(obj, str):
                recs.append({"image": obj})
            else:
                raise SystemExit(f"ERROR: unsupported record at {path}:{lineno}")
    return recs


def _scalar(value):
    if isinstance(value, dict):
        for key in PATHY_KEYS:
            if key in value:
                return _scalar(value[key])
        return None
    if isinstance(value, str) and value:
        return value
    return None


def get_field(rec, keys):
    for key in keys:
        if key in rec:
            got = _scalar(rec[key])
            if got:
                return got
    for container in ("files", "paths", "assets"):
        sub = rec.get(container)
        if isinstance(sub, dict):
            for key in keys:
                if key in sub:
                    got = _scalar(sub[key])
                    if got:
                        return got
    return None


def resolve_path(raw, bases):
    p = Path(raw)
    if p.is_absolute():
        return p
    for base in bases:
        cand = Path(base) / p
        if cand.exists():
            return cand
    return Path(bases[0]) / p


def record_paths(rec, bases):
    img = get_field(rec, IMG_KEYS)
    dep = get_field(rec, DEP_KEYS)
    return (resolve_path(img, bases) if img else None, resolve_path(dep, bases) if dep else None)


def load_depth_npy(path: Path):
    """Load a metric depth map and normalise it to float32 metres.

    INPUT_MANIFEST declares VKITTI2 native uint16 centimetres / 100.  Integer
    arrays are therefore divided by 100, and float arrays are treated as
    metres unless their finite maximum is clearly centimetre-scaled.
    """
    import numpy as np

    arr = np.load(path)
    if arr.dtype.kind in "iu":
        return np.asarray(arr, dtype=np.float32) / 100.0
    arr = np.asarray(arr, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if finite.size and float(finite.max()) > 200.0:
        arr = arr / 100.0
    return arr


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #


def cmd_doctor(args) -> int:
    ok, missing = [], []
    inp = Path(args.input)

    if inp.is_dir():
        ok.append(f"input dir present: {inp}")
    else:
        missing.append(f"input dir missing/not a directory: {inp}")

    bases = [inp, inp.parent, Path.cwd()]
    for name in ("train.jsonl", "validation.jsonl"):
        fp = inp / name
        if not fp.exists():
            missing.append(f"missing {fp}")
            continue
        try:
            recs = load_jsonl(fp)
        except SystemExit as exc:
            missing.append(str(exc))
            continue
        if not recs:
            missing.append(f"empty split: {fp}")
        else:
            ok.append(f"{name}: {len(recs)} records")
        need_depth = name == "train.jsonl"
        for idx, rec in enumerate(recs):
            img, dep = record_paths(rec, bases)
            if img is None or not img.exists():
                missing.append(f"{name}[{idx}] image missing: {img}")
            if need_depth and (dep is None or not dep.exists()):
                missing.append(f"{name}[{idx}] depth missing: {dep}")
            if dep is not None and not dep.exists() and not need_depth:
                ok.append(f"{name}[{idx}] has no depth label (held-out, metrics stay hidden)")

    manifest = inp / "manifest.json"
    if manifest.exists():
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
            for name, expected in (meta.get("files") or {}).items():
                fp = inp / name
                if not fp.exists():
                    missing.append(f"manifest file missing: {name}")
                else:
                    got = sha256_file(fp)
                    if got != expected:
                        missing.append(f"sha256 mismatch for {name}: {got} != {expected}")
                    else:
                        ok.append(f"sha256 ok: {name}")
        except Exception as exc:  # noqa: BLE001
            missing.append(f"manifest.json unreadable: {exc}")

    for mod in ("numpy", "torch", "transformers", "PIL"):
        try:
            __import__(mod)
            ok.append(f"python package available: {mod}")
        except Exception as exc:  # noqa: BLE001
            missing.append(f"python package unavailable: {mod} ({exc})")

    try:
        import torch

        if torch.cuda.is_available():
            ok.append(f"CUDA available: {torch.cuda.get_device_name(0)} (torch {torch.__version__})")
        else:
            missing.append("CUDA not available (task requires a real GPU)")
    except Exception as exc:  # noqa: BLE001
        missing.append(f"cannot query CUDA: {exc}")

    model_path = Path(args.model)
    if model_path.is_dir():
        ok.append(f"model dir present: {model_path}")
        if (model_path / "config.json").exists():
            ok.append("model config.json present")
        else:
            missing.append(f"missing {model_path / 'config.json'}")
        if (model_path / "preprocessor_config.json").exists():
            ok.append("preprocessor_config.json present")
        else:
            missing.append(f"missing {model_path / 'preprocessor_config.json'}")
        weights = sorted(model_path.glob("*.safetensors")) + sorted(model_path.glob("*.bin"))
        if weights:
            ok.append(f"model weights present: {weights[0].name}")
        else:
            missing.append(f"no .safetensors/.bin weights in {model_path}")
    else:
        missing.append(f"model dir missing: {model_path}")

    if args.output:
        out = Path(args.output)
        try:
            out.mkdir(parents=True, exist_ok=True)
            probe = out / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            ok.append(f"output dir writable: {out}")
        except Exception as exc:  # noqa: BLE001
            missing.append(f"output dir not writable: {out} ({exc})")

    print(json.dumps({"task_id": TASK_ID, "status": "missing" if missing else "ok",
                      "ok": ok, "missing": missing}, indent=2))
    for item in ok:
        print(f"[ok]      {item}")
    for item in missing:
        print(f"[missing] {item}")
    return 78 if missing else 0


# --------------------------------------------------------------------------- #
# train
# --------------------------------------------------------------------------- #


def _setup_model(model_path: str):
    import torch
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    processor = AutoImageProcessor.from_pretrained(model_path)
    model = AutoModelForDepthEstimation.from_pretrained(model_path)
    return processor, model, torch


_IMG_MEAN = None


def _predict_meters(model, processor, image, target_hw, torch, device):
    import torch.nn.functional as F
    from PIL import Image  # noqa: F401  (image already PIL.Image)

    pixel_values = processor(images=image, return_tensors="pt")["pixel_values"].to(device)
    out = model(pixel_values=pixel_values)
    pred = out.predicted_depth
    if pred.dim() == 3:
        pred = pred.unsqueeze(1)
    pred = F.interpolate(pred, size=target_hw, mode="bilinear", align_corners=False)[:, 0]
    return pred


def cmd_train(args) -> int:
    import numpy as np
    import torch
    from PIL import Image

    if not torch.cuda.is_available():
        print("ERROR: CUDA is required for 'train' but torch.cuda.is_available() is False",
              file=sys.stderr)
        return 1

    inp = Path(args.input)
    out = Path(args.output)
    model_path = str(Path(args.model))
    train_jsonl = inp / "train.jsonl"
    val_jsonl = inp / "validation.jsonl"

    if not inp.is_dir():
        print(f"ERROR: input dir missing: {inp}", file=sys.stderr)
        return 78
    if not train_jsonl.exists():
        print(f"ERROR: missing {train_jsonl}", file=sys.stderr)
        return 78
    if not Path(model_path).is_dir():
        print(f"ERROR: model directory not found: {model_path}", file=sys.stderr)
        return 78

    out.mkdir(parents=True, exist_ok=True)
    recs = load_jsonl(train_jsonl)
    val_recs = load_jsonl(val_jsonl) if val_jsonl.exists() else []
    bases = [inp, inp.parent, Path.cwd()]

    # fail before any GPU work if a declared asset is absent
    for idx, rec in enumerate(recs):
        img_p, dep_p = record_paths(rec, bases)
        if img_p is None or dep_p is None or not img_p.exists() or not dep_p.exists():
            print(f"ERROR: train record {idx} is missing assets: image={img_p} depth={dep_p}",
                  file=sys.stderr)
            return 78
    for idx, rec in enumerate(val_recs):
        img_p, _ = record_paths(rec, bases)
        if img_p is None or not img_p.exists():
            print(f"ERROR: validation record {idx} is missing image: {img_p}", file=sys.stderr)
            return 78

    seed = int(args.seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    device = torch.device("cuda:0")

    processor, model, _ = _setup_model(model_path)
    model.to(device)
    model.train()

    if args.freeze_backbone and hasattr(model, "backbone"):
        for param in model.backbone.parameters():
            param.requires_grad_(False)

    trainable = [p for p in model.parameters() if p.requires_grad]
    if not trainable:
        print("ERROR: no trainable parameters", file=sys.stderr)
        return 1
    n_trainable = int(sum(p.numel() for p in trainable))
    before_norm = float(sum(float(p.detach().norm().item()) for p in trainable))

    optimizer = torch.optim.AdamW(trainable, lr=float(args.lr), betas=(0.9, 0.999),
                                  eps=1e-8, weight_decay=0.0)

    target_steps = max(int(args.epochs) * len(recs), MIN_STEPS)
    losses, grad_norms, valid_counts, step_times, src_used = [], [], [], [], []
    steps_done = 0
    attempts = 0
    max_attempts = target_steps + 4 * len(recs) + MIN_STEPS
    h2d_bytes = 0

    torch.cuda.synchronize()
    train_t0 = time.perf_counter()
    while steps_done < target_steps and attempts < max_attempts:
        rec = recs[attempts % len(recs)]
        attempts += 1
        img_p, dep_p = record_paths(rec, bases)
        target = load_depth_npy(dep_p)
        if target.ndim != 2:
            print(f"ERROR: depth map not 2-D: {dep_p} -> {target.shape}", file=sys.stderr)
            return 1
        height, width = int(target.shape[0]), int(target.shape[1])
        image = Image.open(img_p).convert("RGB")
        if image.size != (width, height):
            image = image.resize((width, height), Image.BILINEAR)

        step_t0 = time.perf_counter()
        tgt = torch.from_numpy(np.ascontiguousarray(target)).to(device).unsqueeze(0)
        pred = _predict_meters(model, processor, image, (height, width), torch, device)
        valid = ((tgt > DEPTH_MIN) & (tgt < DEPTH_MAX)
                 & torch.isfinite(tgt) & torch.isfinite(pred))
        n_valid = int(valid.sum().item())
        if n_valid == 0:
            torch.cuda.synchronize()
            step_times.append(time.perf_counter() - step_t0)
            continue

        loss = (pred - tgt).abs()[valid].mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()

        grad_total = 0.0
        for param in trainable:
            if param.grad is None:
                continue
            if not torch.isfinite(param.grad).all():
                print("ERROR: non-finite gradient detected", file=sys.stderr)
                return 1
            grad_total += float(param.grad.detach().norm().item())
        optimizer.step()
        for param in trainable:
            if not torch.isfinite(param.detach()).all():
                print("ERROR: non-finite weight after optimizer step", file=sys.stderr)
                return 1

        torch.cuda.synchronize()
        step_times.append(time.perf_counter() - step_t0)
        losses.append(float(loss.detach().item()))
        grad_norms.append(grad_total)
        valid_counts.append(n_valid)
        src_used.append(str(img_p))
        steps_done += 1
        # approximate H2D traffic of this step
        h2d_bytes += int(tgt.numel() * tgt.element_size())

    torch.cuda.synchronize()
    train_wall_s = time.perf_counter() - train_t0

    if steps_done < MIN_STEPS:
        print(f"ERROR: only {steps_done} optimizer updates performed, need >= {MIN_STEPS}",
              file=sys.stderr)
        return 1
    after_norm = float(sum(float(p.detach().norm().item()) for p in trainable))

    # ---- held-out inference -> predictions.npy -----------------------------
    model.eval()
    preds, coverage, abs_rels, rmses, sq_err_sum, abs_rel_num, n_metric_px = [], [], [], [], 0.0, 0.0, 0
    per_image = []
    val_h2d = 0
    torch.cuda.synchronize()
    val_t0 = time.perf_counter()
    with torch.no_grad():
        for idx, rec in enumerate(val_recs):
            img_p, dep_p = record_paths(rec, bases)
            image = Image.open(img_p).convert("RGB")
            if dep_p is not None and dep_p.exists():
                gt = load_depth_npy(dep_p)
                height, width = int(gt.shape[0]), int(gt.shape[1])
            else:
                gt = None
                width, height = image.size
            if image.size != (width, height):
                image = image.resize((width, height), Image.BILINEAR)
            pred = _predict_meters(model, processor, image, (height, width), torch, device)
            arr = pred[0].detach().float().cpu().numpy().astype(np.float32)
            preds.append(arr)
            finite = np.isfinite(arr)
            in_range = finite & (arr > DEPTH_MIN) & (arr < DEPTH_MAX)
            cov = float(in_range.mean())
            coverage.append(cov)
            entry = {"index": idx, "image": str(img_p), "shape": [height, width],
                     "coverage": cov, "pred_min": float(arr[finite].min()) if finite.any() else None,
                     "pred_max": float(arr[finite].max()) if finite.any() else None}
            if gt is not None:
                gtf = np.asarray(gt, dtype=np.float32)
                mask = (gtf > DEPTH_MIN) & (gtf < DEPTH_MAX) & np.isfinite(gtf) & finite
                n_px = int(mask.sum())
                if n_px > 0 and gtf.shape == arr.shape:
                    diff = arr[mask] - gtf[mask]
                    abs_rel = float(np.mean(np.abs(diff) / gtf[mask]))
                    rmse = float(np.sqrt(np.mean(diff ** 2)))
                    abs_rels.append(abs_rel)
                    rmses.append(rmse)
                    abs_rel_num += float(np.sum(np.abs(diff) / gtf[mask]))
                    sq_err_sum += float(np.sum(diff ** 2))
                    n_metric_px += n_px
                    entry["abs_rel"] = abs_rel
                    entry["rmse"] = rmse
                    entry["labelled_pixels"] = n_px
                else:
                    entry["note"] = "no valid labelled pixels"
            per_image.append(entry)
            val_h2d += 1
    torch.cuda.synchronize()
    val_wall_s = time.perf_counter() - val_t0

    if preds:
        shapes = {a.shape for a in preds}
        if len(shapes) == 1:
            pred_arr = np.stack(preds).astype(np.float32)
        else:
            hmax = max(a.shape[0] for a in preds)
            wmax = max(a.shape[1] for a in preds)
            pred_arr = np.full((len(preds), hmax, wmax), np.nan, dtype=np.float32)
            for i, a in enumerate(preds):
                pred_arr[i, : a.shape[0], : a.shape[1]] = a
    else:
        pred_arr = np.zeros((0, 0, 0), dtype=np.float32)

    pred_path = out / "predictions.npy"
    np.save(pred_path, pred_arr)

    ckpt_dir = out / "checkpoint"
    model.save_pretrained(str(ckpt_dir))
    processor.save_pretrained(str(ckpt_dir))

    state = {
        "step": steps_done,
        "optimizer": optimizer.state_dict(),
        "lr": float(args.lr),
        "seed": seed,
        "losses": losses,
        "grad_norms": grad_norms,
        "valid_pixel_counts": valid_counts,
        "rng": {
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "torch_cpu": torch.get_rng_state(),
            "torch_cuda": torch.cuda.get_rng_state_all(),
        },
    }
    torch.save(state, out / "train_state.pt")

    metrics = {
        "abs_rel": float(np.mean(abs_rels)) if abs_rels else None,
        "rmse": float(np.sqrt(sq_err_sum / n_metric_px)) if n_metric_px else None,
        "labelled_pixels": int(n_metric_px),
        "source": "held-out local labels" if n_metric_px else "hidden (no local labels supplied)",
    }

    run = {
        "task_id": TASK_ID,
        "scale": "debug_only",
        "variant": "debug",
        "formal_large_tested": False,
        "model_repo": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_path": model_path,
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "seed": seed,
        "depth_unit": "meters",
        "valid_mask_metres": [DEPTH_MIN, DEPTH_MAX],
        "train": {
            "records": len(recs),
            "steps": steps_done,
            "target_steps": target_steps,
            "epochs": int(args.epochs),
            "lr": float(args.lr),
            "freeze_backbone": bool(args.freeze_backbone),
            "trainable_parameters": n_trainable,
            "loss": "mean absolute error over valid pixels (metres)",
            "final_loss": losses[-1] if losses else None,
            "first_loss": losses[0] if losses else None,
            "losses": losses,
            "grad_norms": grad_norms,
            "weight_norm_before": before_norm,
            "weight_norm_after": after_norm,
            "weights_updated": bool(abs(after_norm - before_norm) > 0.0),
            "images_used": src_used,
            "wall_s": train_wall_s,
            "step_wall_s": step_times,
            "h2d_bytes": h2d_bytes,
        },
        "validation": {
            "records": len(val_recs),
            "predictions_file": str(pred_path),
            "shape": list(pred_arr.shape),
            "dtype": str(pred_arr.dtype),
            "units": "meters",
            "coverage_mean": float(np.mean(coverage)) if coverage else None,
            "coverage_per_image": coverage,
            "per_image": per_image,
            "wall_s": val_wall_s,
            "h2d_images": val_h2d,
        },
        "metrics": metrics,
        "checkpoint": str(ckpt_dir),
        "train_state": str(out / "train_state.pt"),
    }
    (out / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    (out / "predictions_meta.json").write_text(
        json.dumps({"task_id": TASK_ID, "file": str(pred_path), "shape": list(pred_arr.shape),
                    "dtype": "float32", "units": "meters", "per_image": per_image}, indent=2),
        encoding="utf-8")

    print(f"train: {steps_done} updates, first_loss={losses[0]:.4f}, last_loss={losses[-1]:.4f}")
    print(f"predictions: {pred_arr.shape} float32 metres -> {pred_path}")
    print(f"checkpoint: {ckpt_dir}")
    print(f"metrics: abs_rel={metrics['abs_rel']} rmse={metrics['rmse']} ({metrics['source']})")
    return 0


# --------------------------------------------------------------------------- #
# predict (fresh process reload)
# --------------------------------------------------------------------------- #


def cmd_predict(args) -> int:
    import numpy as np
    import torch
    from PIL import Image

    if not torch.cuda.is_available():
        print("ERROR: CUDA is required for 'predict' but torch.cuda.is_available() is False",
              file=sys.stderr)
        return 1

    ckpt = Path(args.checkpoint)
    if not ckpt.is_dir() or not (ckpt / "config.json").exists():
        print(f"ERROR: checkpoint missing or incomplete: {ckpt}", file=sys.stderr)
        return 78
    inp = Path(args.input)
    if not inp.exists():
        print(f"ERROR: input manifest missing: {inp}", file=sys.stderr)
        return 78
    recs = load_jsonl(inp)
    if not recs:
        print(f"ERROR: no records in {inp}", file=sys.stderr)
        return 78
    bases = [inp.parent, inp.parent.parent if inp.parent.parent else inp.parent, Path.cwd()]
    for idx, rec in enumerate(recs):
        img_p, _ = record_paths(rec, bases)
        if img_p is None or not img_p.exists():
            print(f"ERROR: record {idx} image missing: {img_p}", file=sys.stderr)
            return 78

    device = torch.device("cuda:0")
    processor, model, _ = _setup_model(str(ckpt))
    model.to(device).eval()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    preds, coverage, per_image = [], [], []
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        for idx, rec in enumerate(recs):
            img_p, dep_p = record_paths(rec, bases)
            image = Image.open(img_p).convert("RGB")
            if dep_p is not None and dep_p.exists():
                gt = load_depth_npy(dep_p)
                height, width = int(gt.shape[0]), int(gt.shape[1])
            else:
                width, height = image.size
            if image.size != (width, height):
                image = image.resize((width, height), Image.BILINEAR)
            pred = _predict_meters(model, processor, image, (height, width), torch, device)
            arr = pred[0].detach().float().cpu().numpy().astype(np.float32)
            preds.append(arr)
            finite = np.isfinite(arr)
            in_range = finite & (arr > DEPTH_MIN) & (arr < DEPTH_MAX)
            cov = float(in_range.mean())
            coverage.append(cov)
            per_image.append({"index": idx, "image": str(img_p), "shape": [height, width],
                              "coverage": cov,
                              "pred_min": float(arr[finite].min()) if finite.any() else None,
                              "pred_max": float(arr[finite].max()) if finite.any() else None})
    torch.cuda.synchronize()
    wall_s = time.perf_counter() - t0

    shapes = {a.shape for a in preds}
    if len(shapes) == 1:
        pred_arr = np.stack(preds).astype(np.float32)
    else:
        hmax = max(a.shape[0] for a in preds)
        wmax = max(a.shape[1] for a in preds)
        pred_arr = np.full((len(preds), hmax, wmax), np.nan, dtype=np.float32)
        for i, a in enumerate(preds):
            pred_arr[i, : a.shape[0], : a.shape[1]] = a

    np.save(out_path, pred_arr)
    meta = {"task_id": TASK_ID, "checkpoint": str(ckpt), "input": str(inp),
            "output": str(out_path), "shape": list(pred_arr.shape), "dtype": "float32",
            "units": "meters", "coverage_mean": float(np.mean(coverage)) if coverage else None,
            "wall_s": wall_s, "per_image": per_image}
    (out_path.parent / (out_path.name + ".json")).write_text(json.dumps(meta, indent=2),
                                                              encoding="utf-8")
    print(f"predict: {pred_arr.shape} float32 metres -> {out_path}")
    print(f"coverage_mean={meta['coverage_mean']} wall_s={wall_s:.3f}")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-B10 debug variant: adapt an outdoor metric monocular depth model "
                    "(Depth Anything V2 Metric Outdoor Small) on VKITTI2 and export metric depth.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="inspect required inputs/dependencies without running a model")
    d.add_argument("--input", required=True)
    d.add_argument("--output", default=None)
    d.add_argument("--model", default=DEFAULT_MODEL)

    t = sub.add_parser("train", help="fine-tune on VKITTI2 RGB + metric depth (CUDA required)")
    t.add_argument("--input", required=True)
    t.add_argument("--output", required=True)
    t.add_argument("--model", default=DEFAULT_MODEL)
    t.add_argument("--epochs", type=int, default=1)
    t.add_argument("--lr", type=float, default=1e-5)
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--freeze-backbone", action="store_true",
                   help="train only the depth head (backbone frozen)")

    p = sub.add_parser("predict", help="reload a saved checkpoint in a fresh process and predict")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "train":
        return cmd_train(args)
    if args.cmd == "predict":
        return cmd_predict(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
