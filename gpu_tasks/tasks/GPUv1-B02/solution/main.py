#!/usr/bin/env python3
"""GPUv1-B02 (debug variant): build a reloadable object-detection catalogue.

Uses the official TorchVision RetinaNet ResNet50-FPN COCO checkpoint declared
in /models/torchvision/retinanet.json and runs detection on the 16 genuine
COCO val2017 images listed in input/images.json on CUDA.

Subcommands:
  detect --input DIR --output DIR      run detection, write deliverables
  query  --catalog FILE --image-id ID  print stored detection JSON for one image
  doctor --input DIR                   inspect required inputs/deps without
                                       executing training/inference
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

MODEL_CFG_DEFAULT = "/models/torchvision/retinanet.json"
SCORE_THRESHOLD = 0.25
MIN_SIZE = 320
MAX_SIZE = 640
NUM_CLASSES = 91
TASK_ID = "GPUv1-B02-debug"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-B02 debug: RetinaNet catalogue over COCO images.",
    )
    sub = p.add_subparsers(dest="cmd")

    d = sub.add_parser("detect", help="Run detection and write catalogue outputs.")
    d.add_argument("--input", required=True, help="input directory")
    d.add_argument("--output", required=True, help="output directory")

    q = sub.add_parser("query", help="Print stored detections for one image.")
    q.add_argument("--catalog", required=True, help="path to output/catalog.json")
    q.add_argument("--image-id", required=True, help="image_id to look up")

    h = sub.add_parser("doctor", help="Inspect inputs/deps without running GPU work.")
    h.add_argument("--input", required=True, help="input directory")
    return p


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# model config / weights resolution
# --------------------------------------------------------------------------- #
def load_model_cfg(path=MODEL_CFG_DEFAULT):
    p = Path(path)
    if not p.is_file():
        return None, f"model config not found: {path}"
    try:
        return json.loads(p.read_text()), None
    except Exception as exc:
        return None, f"failed to parse {path}: {exc}"


def _collect_strings(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_strings(v, out)


def _candidate_base_dirs(cfg_path):
    bases = []
    if cfg_path:
        bases.append(str(Path(cfg_path).parent))
    bases += [
        "/models/torchvision",
        "/models",
        os.path.expanduser("~/.cache/torch/hub/checkpoints"),
        "/root/.cache/torch/hub/checkpoints",
    ]
    seen, out = set(), []
    for b in bases:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def resolve_weights(cfg, cfg_path=MODEL_CFG_DEFAULT):
    """Return a local checkpoint path or None."""
    bases = _candidate_base_dirs(cfg_path)
    declared = []
    if isinstance(cfg, dict):
        strings = []
        _collect_strings(cfg, strings)
        for s in strings:
            base = os.path.basename(s.split("?")[0])
            if base.lower().endswith((".pth", ".pt", ".ckpt", ".pth.tar")):
                declared.append(base)

    for name in declared:
        for b in bases:
            p = os.path.join(b, name)
            if os.path.isfile(p):
                return p

    for name in declared:
        stem = Path(name).stem
        if not stem:
            continue
        for b in bases:
            if not os.path.isdir(b):
                continue
            for f in sorted(os.listdir(b)):
                if stem in f and os.path.isfile(os.path.join(b, f)):
                    return os.path.join(b, f)

    for b in bases:
        if not os.path.isdir(b):
            continue
        for pat in ("*retinanet*.pth", "*retinanet*.pt"):
            m = sorted(Path(b).glob(pat))
            if m:
                return str(m[0])
    return None


# --------------------------------------------------------------------------- #
# images.json normalisation
# --------------------------------------------------------------------------- #
def extract_image_entries(data):
    seq = None
    if isinstance(data, list):
        seq = data
    elif isinstance(data, dict):
        for key in ("images", "data", "items", "entries", "files"):
            v = data.get(key)
            if isinstance(v, list):
                seq = v
                break
    if seq is None:
        return []
    entries = []
    for item in seq:
        if isinstance(item, str):
            fn = item
            iid = None
        elif isinstance(item, dict):
            fn = item.get("file_name") or item.get("filename") or item.get("path")
            iid = item.get("image_id")
            if iid is None:
                iid = item.get("id")
        else:
            continue
        if not fn:
            continue
        if iid is None:
            stem = Path(str(fn)).stem
            iid = int(stem) if stem.isdigit() else stem
        entries.append({"image_id": iid, "file_name": fn})
    return entries


# --------------------------------------------------------------------------- #
# strict checkpoint loading (no remap, metadata preserved)
# --------------------------------------------------------------------------- #
_WRAPPER_KEYS = (
    "model",
    "state_dict",
    "model_state_dict",
    "weights",
    "network",
    "model_ema",
    "ema_state_dict",
)


def _iter_state_dict_candidates(raw):
    """Yield (label, candidate_object) without creating new dicts.

    Each candidate is yielded as-is so that OrderedDict._metadata (which
    TorchVision's RetinaNet uses for legacy head version migration via
    _load_from_state_dict) is preserved end-to-end.
    """
    if isinstance(raw, dict):
        yield "top_level", raw
        for k in _WRAPPER_KEYS:
            v = raw.get(k)
            if isinstance(v, dict):
                yield k, v


def _build_model():
    """Instantiate a fresh, randomly initialized RetinaNet with the exact
    declared parameters.  Returns (model, torchvision_version_string)."""
    import torchvision
    from torchvision.models.detection import retinanet_resnet50_fpn

    model = retinanet_resnet50_fpn(
        weights=None,
        weights_backbone=None,
        num_classes=NUM_CLASSES,
        min_size=MIN_SIZE,
        max_size=MAX_SIZE,
    )
    return model, torchvision.__version__


def load_pretrained_retinanet(weights_path):
    """Strictly load the declared RetinaNet checkpoint.

    - Reads the checkpoint, unwrapping only well-known container keys
      (``model``, ``state_dict``, ...) without rebuilding the OrderedDict, so
      the TorchVision RetinaNet head-version ``_metadata`` travels with it.
    - Instantiates retinanet_resnet50_fpn(weights=None, weights_backbone=None,
      num_classes=91, min_size=320, max_size=640).
    - Calls model.load_state_dict(state, strict=True) directly.  Any missing
      or unexpected key raises; we never accept partial coverage and never
      silently keep randomly-initialized layers.

    Returns (model, info_dict).  Raises RuntimeError on failure.
    """
    import torch

    raw = torch.load(weights_path, map_location="cpu", weights_only=False)

    errors = []
    for label, cand in _iter_state_dict_candidates(raw):
        # Fresh model per attempt: load_state_dict copies parameters before
        # raising on strict-key checks, so a failed attempt would leave the
        # model in a partially loaded state.
        model, tv_ver = _build_model()
        try:
            model.load_state_dict(cand, strict=True)
        except RuntimeError as exc:
            msg = str(exc)
            errors.append({"wrapper": label, "error": msg[:2000]})
            continue
        except Exception as exc:  # defensive
            errors.append({"wrapper": label, "error": repr(exc)[:2000]})
            continue
        info = {
            "wrapper": label,
            "strict_load": True,
            "torchvision_version": tv_ver,
            "num_classes": NUM_CLASSES,
            "min_size": MIN_SIZE,
            "max_size": MAX_SIZE,
            "param_tensor_count": sum(1 for _ in model.parameters()),
            "state_entry_count": len(list(cand.keys()))
            if hasattr(cand, "keys") else None,
        }
        model.eval()
        return model, info

    raise RuntimeError(
        "strict state_dict load failed for all wrapper candidates: "
        + json.dumps(errors)
    )


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def cmd_doctor(args):
    missing = []
    notes = {}
    inp = Path(args.input)
    if not inp.is_dir():
        missing.append(f"input directory missing: {inp}")
    else:
        imjson = inp / "images.json"
        imdir = inp / "images"
        if not imjson.is_file():
            missing.append(f"missing file: {imjson}")
        if not imdir.is_dir():
            missing.append(f"missing directory: {imdir}")
        elif imjson.is_file():
            try:
                entries = extract_image_entries(json.loads(imjson.read_text()))
                if not entries:
                    missing.append(
                        f"images.json parsed but yielded no entries: {imjson}"
                    )
                for e in entries:
                    p = imdir / e["file_name"]
                    if not p.is_file():
                        missing.append(f"missing image: {p}")
                notes["num_images"] = len(entries)
            except Exception as exc:
                missing.append(f"failed to read {imjson}: {exc}")

    cfg, err = load_model_cfg()
    weights_path = None
    if err:
        missing.append(err)
    else:
        weights_path = resolve_weights(cfg)
        if weights_path is None:
            missing.append(
                "no local weights resolved from /models/torchvision/retinanet.json"
            )
        else:
            notes["weights_path"] = weights_path

    torch_mod = None
    try:
        import torch as _torch  # noqa: F401
        import torchvision as _tv  # noqa: F401
        torch_mod = _torch
    except Exception as exc:
        missing.append(f"torch/torchvision import failed: {exc}")
    if torch_mod is not None and not torch_mod.cuda.is_available():
        missing.append("CUDA not available (torch.cuda.is_available()==False)")

    if not missing and weights_path is not None:
        try:
            _m, info = load_pretrained_retinanet(weights_path)
            notes["wrapper"] = info["wrapper"]
            notes["strict_load"] = info["strict_load"]
            notes["torchvision_version"] = info["torchvision_version"]
            notes["num_classes"] = info["num_classes"]
            notes["min_size"] = info["min_size"]
            notes["max_size"] = info["max_size"]
        except Exception as exc:
            missing.append(f"strict checkpoint load failed: {exc}")

    if missing:
        for m in missing:
            print(f"MISSING: {m}", file=sys.stderr)
        return 78
    print("doctor: all required inputs and dependencies present")
    for k, v in notes.items():
        print(f"  {k}: {v}")
    return 0


# --------------------------------------------------------------------------- #
# detect
# --------------------------------------------------------------------------- #
def cmd_detect(args):
    try:
        import numpy as np
        import torch
        import torchvision
        from PIL import Image
    except Exception as exc:
        print(f"ERROR: import failure: {exc}", file=sys.stderr)
        return 78

    if not torch.cuda.is_available():
        print("ERROR: CUDA is required but not available", file=sys.stderr)
        return 1

    inp = Path(args.input)
    out = Path(args.output)
    imjson = inp / "images.json"
    if not imjson.is_file():
        print(f"ERROR: missing {imjson}", file=sys.stderr)
        return 78

    cfg, err = load_model_cfg()
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 78
    weights_path = resolve_weights(cfg)
    if weights_path is None:
        print("ERROR: cannot resolve retinanet weights path", file=sys.stderr)
        return 78

    entries = extract_image_entries(json.loads(imjson.read_text()))
    if not entries:
        print("ERROR: images.json yielded no entries", file=sys.stderr)
        return 1

    out.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)

    try:
        model, info = load_pretrained_retinanet(weights_path)
    except Exception as exc:
        print(f"ERROR: failed to load model: {exc}", file=sys.stderr)
        return 1
    model.to(device).eval()

    weights_sha = sha256_file(weights_path)

    try:
        from torchvision.models.detection import RetinaNet_ResNet50_FPN_Weights
        cats_meta = list(
            RetinaNet_ResNet50_FPN_Weights.COCO_V1.meta["categories"]
        )
    except Exception:
        cats_meta = None
    if not cats_meta:
        cats_meta = [f"class_{i}" for i in range(NUM_CLASSES)]
    categories = {str(i): c for i, c in enumerate(cats_meta)}

    detections = []
    index = {}
    per_image_times = []
    num_boxes_total = 0
    session_start = time.perf_counter()

    for i, entry in enumerate(entries):
        fn = entry["file_name"]
        iid = entry["image_id"]
        img_path = inp / "images" / fn
        if not img_path.is_file():
            print(f"ERROR: missing image {img_path}", file=sys.stderr)
            return 78

        with Image.open(img_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            arr = np.asarray(im, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(arr).permute(2, 0, 1).contiguous().to(device)

        torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            preds = model([tensor])
        torch.cuda.synchronize()
        t1 = time.perf_counter()
        per_image_times.append(t1 - t0)

        pred = preds[0]
        boxes = pred["boxes"].detach().cpu().numpy()
        labels = pred["labels"].detach().cpu().numpy()
        scores = pred["scores"].detach().cpu().numpy()
        keep = scores >= SCORE_THRESHOLD
        boxes = boxes[keep]
        labels = labels[keep]
        scores = scores[keep]

        if boxes.size:
            boxes[:, 0] = np.clip(boxes[:, 0], 0, width)
            boxes[:, 1] = np.clip(boxes[:, 1], 0, height)
            boxes[:, 2] = np.clip(boxes[:, 2], 0, width)
            boxes[:, 3] = np.clip(boxes[:, 3], 0, height)
            order = np.argsort(-scores, kind="stable")
            boxes = boxes[order]
            labels = labels[order]
            scores = scores[order]

        num_boxes_total += int(boxes.shape[0])
        rec = {
            "image_id": iid,
            "file_name": fn,
            "original_size": [int(width), int(height)],
            "boxes": [[float(v) for v in b] for b in boxes.tolist()],
            "labels": [int(v) for v in labels.tolist()],
            "scores": [float(v) for v in scores.tolist()],
        }
        detections.append(rec)
        index[str(iid)] = i

    wall = time.perf_counter() - session_start

    det_doc = {
        "model_name": "retinanet_resnet50_fpn",
        "weights_sha256": weights_sha,
        "min_size": MIN_SIZE,
        "max_size": MAX_SIZE,
        "score_threshold": SCORE_THRESHOLD,
        "num_classes": len(cats_meta),
        "categories": categories,
        "num_images": len(detections),
        "num_boxes": num_boxes_total,
        "detections": detections,
    }
    (out / "detections.json").write_text(json.dumps(det_doc))

    catalog = {
        "task_id": TASK_ID,
        "model_name": "retinanet_resnet50_fpn",
        "weights_path": str(weights_path),
        "weights_sha256": weights_sha,
        "min_size": MIN_SIZE,
        "max_size": MAX_SIZE,
        "score_threshold": SCORE_THRESHOLD,
        "num_classes": len(cats_meta),
        "categories": categories,
        "detections_file": "detections.json",
        "num_images": len(detections),
        "num_boxes": num_boxes_total,
        "images": index,
    }
    (out / "catalog.json").write_text(json.dumps(catalog))

    run = {
        "task_id": TASK_ID,
        "command": "detect",
        "device_name": torch.cuda.get_device_name(0),
        "device_count": torch.cuda.device_count(),
        "torch_version": torch.__version__,
        "torchvision_version": torchvision.__version__,
        "cuda_version": torch.version.cuda,
        "wall_seconds": wall,
        "per_image_seconds": per_image_times,
        "mean_image_seconds": (
            float(sum(per_image_times) / len(per_image_times))
            if per_image_times else None
        ),
        "num_images": len(detections),
        "num_boxes": num_boxes_total,
        "weights_path": str(weights_path),
        "weights_sha256": weights_sha,
        "architecture": "retinanet_resnet50_fpn",
        "strict_load": info["strict_load"],
        "checkpoint_wrapper": info["wrapper"],
        "checkpoint_state_entries": info["state_entry_count"],
        "min_size": MIN_SIZE,
        "max_size": MAX_SIZE,
        "score_threshold": SCORE_THRESHOLD,
        "num_classes": NUM_CLASSES,
        "seed": 0,
        "synchronized_timings": True,
    }
    (out / "run.json").write_text(json.dumps(run))

    print(
        f"detect[retinanet_resnet50_fpn strict]: {len(detections)} images, "
        f"{num_boxes_total} boxes, wall={wall:.2f}s"
    )
    return 0


# --------------------------------------------------------------------------- #
# query
# --------------------------------------------------------------------------- #
def cmd_query(args):
    cat_path = Path(args.catalog)
    if not cat_path.is_file():
        print(f"ERROR: missing catalog {cat_path}", file=sys.stderr)
        return 78
    try:
        catalog = json.loads(cat_path.read_text())
    except Exception as exc:
        print(f"ERROR: bad catalog: {exc}", file=sys.stderr)
        return 1

    det_file = Path(catalog.get("detections_file", "detections.json"))
    if not det_file.is_absolute():
        det_file = cat_path.parent / det_file
    if not det_file.is_file():
        print(f"ERROR: missing detections file {det_file}", file=sys.stderr)
        return 78
    dets = json.loads(det_file.read_text())

    key = str(args.image_id)
    index = catalog.get("images", {})
    if key not in index:
        print(f"ERROR: image_id {args.image_id} not present in catalog",
              file=sys.stderr)
        return 1
    idx = index[key]
    try:
        rec = dets["detections"][idx]
    except (KeyError, IndexError, TypeError) as exc:
        print(f"ERROR: catalogue index inconsistent: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(rec, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
        return 0
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "detect":
        return cmd_detect(args)
    if args.cmd == "query":
        return cmd_query(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
