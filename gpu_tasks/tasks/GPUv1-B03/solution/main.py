#!/usr/bin/env python3
"""GPUv1-B03 (debug variant) - TorchVision Mask R-CNN ResNet50-FPN instance
segmentation training on 12 real COCO images (with instance polygons/RLE),
then full-image prediction on all 16 images exporting COCO RLE masks and
original-image-space outer contour polygons.

Subcommands
-----------
    train   --input input --output output
    predict --checkpoint output/checkpoint.pt --input input --output output/reloaded
    doctor  --input input

All real work requires CUDA.  Missing inputs return exit code 78 (EX_CONFIG).
"""

import argparse
import json
import os
import random
import sys
import time


TASK_ID = "GPUv1-B03"
WEIGHTS_SPEC = "/models/torchvision/maskrcnn.json"
MIN_SIZE = 320
MAX_SIZE = 640
NUM_CLASSES = 91
SCORE_THRESH = 0.25
MASK_THRESH = 0.5


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def make_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-B03: fine-tune Mask R-CNN ResNet50-FPN on COCO "
                    "instance annotations and export RLE masks + contours.",
    )
    sub = p.add_subparsers(dest="command")

    pt = sub.add_parser("train",
                        help="one optimizer update per annotated training image")
    pt.add_argument("--input", required=True)
    pt.add_argument("--output", required=True)

    pp = sub.add_parser("predict",
                        help="run inference on every image and export instances/contours")
    pp.add_argument("--checkpoint", required=True)
    pp.add_argument("--input", required=True)
    pp.add_argument("--output", required=True)

    pd = sub.add_parser("doctor",
                        help="inspect required files and dependencies without running")
    pd.add_argument("--input", required=True)

    return p


# --------------------------------------------------------------------------- #
# small helpers                                                               #
# --------------------------------------------------------------------------- #

def _require_cuda():
    import torch
    if not torch.cuda.is_available():
        sys.stderr.write("ERROR: CUDA is required but not available\n")
        raise SystemExit(3)
    return torch


def _load_images_json(path):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        for key in ("images", "data", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError("images.json has no 'images' list; keys=%s" % list(data.keys()))
    return data


def _find_image_path(input_dir, file_name):
    if not file_name:
        return None
    for cand in (os.path.join(input_dir, "images", file_name),
                 os.path.join(input_dir, file_name)):
        if os.path.isfile(cand):
            return cand
    return None


def _resolve_image_file(input_dir, img_id, meta, coco=None):
    """Return (path, file_name).  Raises SystemExit(78) if the image is absent."""
    candidates = []
    if meta:
        for k in ("file_name", "file", "path", "coco_url"):
            if isinstance(meta.get(k), str):
                candidates.append(os.path.basename(meta[k]))
    if coco is not None:
        try:
            ims = coco.loadImgs([img_id])
            if ims and isinstance(ims[0].get("file_name"), str):
                candidates.append(os.path.basename(ims[0]["file_name"]))
        except Exception:
            pass
    if img_id is not None:
        try:
            candidates.append("%012d.jpg" % int(img_id))
            candidates.append("%d.jpg" % int(img_id))
        except Exception:
            pass
    for name in candidates:
        p = _find_image_path(input_dir, name)
        if p:
            return p, name
    sys.stderr.write("ERROR: missing image file for id %s (tried %s)\n"
                     % (img_id, candidates))
    raise SystemExit(78)


def _load_rgb_array(path):
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        arr = np.array(im.convert("RGB"))
    return np.ascontiguousarray(arr)


# --------------------------------------------------------------------------- #
# weights resolution                                                          #
# --------------------------------------------------------------------------- #

def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(k)
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)


def _unwrap_state_dict(obj):
    """Given an object loaded via torch.load, try to extract a
    parameter->tensor mapping.  Returns None if not possible."""
    import torch
    for _ in range(4):
        if not isinstance(obj, dict):
            return None
        # direct state dict?
        if any(isinstance(v, torch.Tensor) for v in obj.values()):
            # strip DataParallel 'module.' prefix if present
            if all((not isinstance(k, str)) or k.startswith("module.") for k in obj.keys()):
                obj = {k[len("module."):] if isinstance(k, str) else k: v
                       for k, v in obj.items()}
            return obj
        # wrapped?
        wrapped = False
        for key in ("model", "state_dict", "model_state_dict", "weights", "params"):
            inner = obj.get(key)
            if isinstance(inner, dict) and any(isinstance(v, torch.Tensor)
                                               for v in inner.values()):
                obj = inner
                wrapped = True
                break
        if not wrapped:
            return None
    return None


def _try_extract_state_dict(path):
    import torch
    try:
        obj = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as e:
        sys.stderr.write("warn: torch.load(%s) failed: %s\n" % (path, e))
        return None
    sd = _unwrap_state_dict(obj)
    if sd is not None:
        return sd
    sys.stderr.write("warn: %s did not contain a state_dict\n" % path)
    return None


def _resolve_weights_spec():
    """Resolve initial weights from WEIGHTS_SPEC.  Returns a dict:

        {'kind': 'state_dict',    'state': {...}, 'path': ...}
        {'kind': 'enum_maskrcnn', 'enum': <MRW enum>}
        {'kind': 'enum_resnet',   'enum': <R50 enum>}

    Raises SystemExit(78) if resolution fails.
    """
    import torch  # noqa: F401
    if not os.path.isfile(WEIGHTS_SPEC):
        sys.stderr.write("ERROR: missing weights spec %s\n" % WEIGHTS_SPEC)
        raise SystemExit(78)
    try:
        with open(WEIGHTS_SPEC) as f:
            spec = json.load(f)
    except Exception as e:
        sys.stderr.write("ERROR: cannot parse %s: %s\n" % (WEIGHTS_SPEC, e))
        raise SystemExit(78)

    spec_dir = os.path.dirname(os.path.abspath(WEIGHTS_SPEC))
    parent_dir = os.path.dirname(spec_dir)

    all_strings = [s for s in _walk_strings(spec) if isinstance(s, str)]

    # --- Stage 1: any string as a local file path (as-is or relative to spec dir)
    for s in all_strings:
        for base in ("", spec_dir, parent_dir, "."):
            cand = os.path.join(base, s) if base else s
            if cand and os.path.isfile(cand):
                sd = _try_extract_state_dict(cand)
                if sd is not None:
                    return {"kind": "state_dict", "state": sd,
                            "path": os.path.abspath(cand)}

    # --- Stage 2: try stem + common extension relative to spec dir / parent
    for s in all_strings:
        stem = os.path.splitext(os.path.basename(s))[0]
        if not stem:
            continue
        for ext in (".pth", ".pt", ".pkl", ".bin", ".ckpt", ".tar"):
            for base in (spec_dir, parent_dir):
                cand = os.path.join(base, stem + ext)
                if os.path.isfile(cand):
                    sd = _try_extract_state_dict(cand)
                    if sd is not None:
                        return {"kind": "state_dict", "state": sd,
                                "path": os.path.abspath(cand)}

    # --- Stage 3: name-based enum resolution against torchvision
    from torchvision.models.detection import MaskRCNN_ResNet50_FPN_Weights as MRW
    try:
        from torchvision.models import ResNet50_Weights as R50W
    except Exception:
        R50W = None

    def try_enum(candidate):
        if not isinstance(candidate, str):
            return None
        variants = {candidate, candidate.strip(), candidate.strip().upper()}
        for c in variants:
            if not c:
                continue
            # dotted like "MaskRCNN_ResNet50_FPN_Weights.COCO_V1" or "ResNet50_Weights.IMAGENET1K_V1"
            if "." in c:
                parts = c.split(".")
                member = parts[-1]
                prefix = ".".join(parts[:-1])
                if "MaskRCNN" in prefix and hasattr(MRW, member):
                    return {"kind": "enum_maskrcnn", "enum": getattr(MRW, member)}
                if R50W is not None and ("ResNet" in prefix or "R50" in prefix) \
                        and hasattr(R50W, member):
                    return {"kind": "enum_resnet", "enum": getattr(R50W, member)}
            # plain member name
            if hasattr(MRW, c):
                return {"kind": "enum_maskrcnn", "enum": getattr(MRW, c)}
            if R50W is not None and hasattr(R50W, c):
                return {"kind": "enum_resnet", "enum": getattr(R50W, c)}
        return None

    for s in all_strings:
        r = try_enum(s)
        if r is not None:
            return r

    # --- Stage 4: heuristic on joined keys/values
    joined = " ".join(all_strings).lower()
    if any(k in joined for k in ("coco", "maskrcnn", "mask_rcnn", "mask-rcnn")):
        return {"kind": "enum_maskrcnn", "enum": MRW.DEFAULT}
    if any(k in joined for k in ("imagenet", "r-50", "r50", "resnet50", "resnet-50")):
        if R50W is not None:
            return {"kind": "enum_resnet", "enum": R50W.IMAGENET1K_V1}

    # --- Stage 5: solitary weights file in spec dir / its parent
    searched_dirs = [spec_dir, parent_dir]
    # also common torch hub cache paths
    home = os.path.expanduser("~")
    searched_dirs += [
        os.path.join(home, ".cache", "torch", "hub", "checkpoints"),
        "/root/.cache/torch/hub/checkpoints",
        "/models",
    ]
    found = []
    for d in searched_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for fn in os.listdir(d):
                if fn.lower().endswith((".pth", ".pt", ".pkl", ".bin")):
                    found.append(os.path.join(d, fn))
        except Exception:
            pass
    for cand in found:
        name = os.path.basename(cand).lower()
        if "mask" in name or "rcnn" in name or "coco" in name:
            sd = _try_extract_state_dict(cand)
            if sd is not None:
                return {"kind": "state_dict", "state": sd,
                        "path": os.path.abspath(cand)}

    # --- Give up: dump the spec for diagnostics
    sys.stderr.write("ERROR: could not resolve weights from %s\n" % WEIGHTS_SPEC)
    try:
        sys.stderr.write("spec contents: %s\n" % json.dumps(spec, default=str))
    except Exception:
        pass
    if found:
        sys.stderr.write("files seen: %s\n" % found)
    raise SystemExit(78)


def _build_model_from_resolved(resolved):
    import torch  # noqa: F401
    from torchvision.models.detection import maskrcnn_resnet50_fpn

    kind = resolved["kind"]
    info = {"kind": kind}

    if kind == "state_dict":
        sd = resolved["state"]
        nc = NUM_CLASSES
        for key in ("roi_heads.box_predictor.cls_score.weight",
                    "roi_heads.box_predictor.cls_score.bias"):
            t = sd.get(key)
            if t is not None and hasattr(t, "shape") and len(t.shape) >= 1:
                nc = int(t.shape[0])
                break
        model = maskrcnn_resnet50_fpn(
            weights=None, weights_backbone=None, num_classes=nc,
            min_size=MIN_SIZE, max_size=MAX_SIZE)
        missing, unexpected = model.load_state_dict(sd, strict=False)
        # ensure a meaningful overlap
        total = len(model.state_dict())
        loaded = total - len(missing)
        info.update(num_classes=nc, missing=len(missing),
                    unexpected=len(unexpected), path=resolved.get("path"),
                    loaded_params=loaded, total_params=total)
        if loaded <= 0:
            sys.stderr.write("ERROR: state_dict has no matching parameters\n")
            raise SystemExit(78)
        return model, info

    if kind == "enum_maskrcnn":
        enum = resolved["enum"]
        model = maskrcnn_resnet50_fpn(weights=enum, min_size=MIN_SIZE,
                                      max_size=MAX_SIZE)
        info["source"] = enum.name
        return model, info

    if kind == "enum_resnet":
        enum = resolved["enum"]
        model = maskrcnn_resnet50_fpn(weights=None, weights_backbone=enum,
                                      num_classes=NUM_CLASSES,
                                      min_size=MIN_SIZE, max_size=MAX_SIZE)
        info["source"] = enum.name
        return model, info

    raise RuntimeError("unhandled weights kind: %r" % kind)


# --------------------------------------------------------------------------- #
# COCO helpers                                                                #
# --------------------------------------------------------------------------- #

def _load_coco(ann_path):
    from pycocotools.coco import COCO
    return COCO(ann_path)


def _build_target(coco, img_id, shape):
    import numpy as np
    import torch
    H, W = shape[0], shape[1]
    ann_ids = coco.getAnnIds(imgIds=[img_id])
    anns = coco.loadAnns(ann_ids)

    boxes, labels, masks, areas = [], [], [], []
    for a in anns:
        if a.get("iscrowd", 0):
            continue
        if not a.get("segmentation"):
            continue
        x, y, w, h = a["bbox"]
        if w <= 0 or h <= 0:
            continue
        x1 = max(0.0, float(x)); y1 = max(0.0, float(y))
        x2 = min(float(W), float(x) + float(w))
        y2 = min(float(H), float(y) + float(h))
        if x2 - x1 < 1.0 or y2 - y1 < 1.0:
            continue
        m = coco.annToMask(a)
        if m.shape != (H, W):
            mm = np.zeros((H, W), dtype=np.uint8)
            hh, ww = min(H, m.shape[0]), min(W, m.shape[1])
            mm[:hh, :ww] = m[:hh, :ww]
            m = mm
        m = (np.asarray(m) > 0).astype(np.uint8)
        if m.sum() == 0:
            continue
        boxes.append([x1, y1, x2, y2])
        labels.append(int(a["category_id"]))
        masks.append(m)
        areas.append(float(a.get("area", (x2 - x1) * (y2 - y1))))

    if not boxes:
        return None

    target = {
        "boxes": torch.tensor(boxes, dtype=torch.float32),
        "labels": torch.tensor(labels, dtype=torch.int64),
        "masks": torch.from_numpy(np.stack(masks, axis=0)).to(torch.uint8),
        "image_id": torch.tensor([int(img_id)], dtype=torch.int64),
        "area": torch.tensor(areas, dtype=torch.float32),
        "iscrowd": torch.zeros(len(boxes), dtype=torch.int64),
    }
    return target


# --------------------------------------------------------------------------- #
# checkpoint                                                                  #
# --------------------------------------------------------------------------- #

def _save_checkpoint(path, model, optimizer, step, extra):
    import numpy as np
    import torch
    ckpt = {
        "format": "GPUv1-B03-checkpoint-v1",
        "task": TASK_ID,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "step": int(step),
        "torch_rng_state": torch.get_rng_state(),
        "cuda_rng_state": torch.cuda.get_rng_state_all(),
        "numpy_rng_state": np.random.get_state(),
        "python_rng_state": random.getstate(),
        "model_config": {
            "arch": "torchvision.models.detection.maskrcnn_resnet50_fpn",
            "min_size": MIN_SIZE,
            "max_size": MAX_SIZE,
            "num_classes": NUM_CLASSES,
            "score_thresh": SCORE_THRESH,
            "mask_thresh": MASK_THRESH,
            "class_convention": "COCO 91-id (background=0, categories 1..90)",
        },
        "extra": extra,
    }
    tmp = path + ".tmp"
    torch.save(ckpt, tmp)
    os.replace(tmp, path)


def _load_checkpoint(path):
    import torch
    from torchvision.models.detection import maskrcnn_resnet50_fpn
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    cfg = ckpt.get("model_config", {})
    model = maskrcnn_resnet50_fpn(
        weights=None, weights_backbone=None,
        num_classes=cfg.get("num_classes", NUM_CLASSES),
        min_size=cfg.get("min_size", MIN_SIZE),
        max_size=cfg.get("max_size", MAX_SIZE),
    )
    model.load_state_dict(ckpt["model_state_dict"], strict=True)
    return model, ckpt


# --------------------------------------------------------------------------- #
# contours                                                                    #
# --------------------------------------------------------------------------- #

def _extract_contours(binary_mask):
    import numpy as np
    if int(binary_mask.sum()) == 0:
        return []

    try:
        import cv2  # type: ignore
        cnts, _ = cv2.findContours(
            binary_mask.astype(np.uint8), cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_NONE)
        out = []
        for c in cnts:
            pts = c.reshape(-1, 2)
            if len(pts) >= 3 and cv2.contourArea(c) >= 1.0:
                out.append(pts.astype(int).tolist())
        if out:
            return out
    except Exception:
        pass

    try:
        from skimage import measure  # type: ignore
        cs = measure.find_contours(binary_mask.astype(float), 0.5)
        out = []
        for c in cs:
            if len(c) >= 3:
                pts = np.stack([c[:, 1], c[:, 0]], axis=1)
                out.append(np.round(pts).astype(int).tolist())
        if out:
            return out
    except Exception:
        pass

    ys, xs = np.where(binary_mask)
    x0, y0 = int(xs.min()), int(ys.min())
    x1, y1 = int(xs.max()), int(ys.max())
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]]


# --------------------------------------------------------------------------- #
# train                                                                       #
# --------------------------------------------------------------------------- #

def cmd_train(args):
    import numpy as np
    import torch

    torch = _require_cuda()
    _ = np
    device = torch.device("cuda")
    t0 = time.time()

    input_dir = args.input
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    train_ann = os.path.join(input_dir, "train_annotations.json")
    images_json = os.path.join(input_dir, "images.json")
    for p in (train_ann, images_json):
        if not os.path.isfile(p):
            sys.stderr.write("ERROR: missing %s\n" % p)
            raise SystemExit(78)

    resolved = _resolve_weights_spec()
    model, load_info = _build_model_from_resolved(resolved)
    model.to(device)
    print(json.dumps({"weights": load_info}), flush=True)

    images_all = _load_images_json(images_json)
    by_id = {int(im["id"]): im for im in images_all if "id" in im}
    coco = _load_coco(train_ann)
    train_ids = sorted(int(i) for i in coco.getImgIds())
    if not train_ids:
        sys.stderr.write("ERROR: no image ids in train_annotations.json\n")
        raise SystemExit(78)

    init_snapshot = {k: v.detach().clone() for k, v in model.state_dict().items()}

    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(trainable, lr=1e-4, momentum=0.9, weight_decay=1e-4)

    step = 0
    losses_log = []
    mask_loss_seen = False

    for img_id in train_ids:
        meta = by_id.get(img_id, {})
        img_path, file_name = _resolve_image_file(input_dir, img_id, meta, coco)
        arr = _load_rgb_array(img_path)
        target = _build_target(coco, img_id, arr.shape)
        if target is None:
            sys.stderr.write("warn: no usable instance masks for %s\n" % file_name)
            continue

        img_t = torch.from_numpy(arr).permute(2, 0, 1).contiguous().float() / 255.0
        img_t = img_t.to(device)
        target = {k: (v.to(device) if torch.is_tensor(v) else v)
                  for k, v in target.items()}

        model.train()
        loss_dict = model([img_t], [target])
        if not isinstance(loss_dict, dict):
            loss_dict = {"loss": sum(loss_dict)}
        if "loss_mask" in loss_dict:
            mask_loss_seen = True
        losses = sum(v for v in loss_dict.values())
        optimizer.zero_grad(set_to_none=True)
        losses.backward()

        gsum = 0.0
        for p in model.parameters():
            if p.grad is not None:
                gsum += float(p.grad.detach().abs().sum().item())
        if gsum <= 0.0:
            raise RuntimeError("no gradient signal after backward for image %s"
                               % file_name)

        optimizer.step()
        step += 1

        entry = {"image_id": int(img_id), "file_name": file_name, "step": step,
                 "grad_sum": gsum}
        for k, v in loss_dict.items():
            entry[k] = float(v.detach().item())
        entry["total"] = float(losses.detach().item())
        losses_log.append(entry)
        print(json.dumps(entry), flush=True)

    if not mask_loss_seen:
        raise RuntimeError("no loss_mask produced -- instance segmentation "
                           "labels missing")
    if step == 0:
        raise RuntimeError("no optimizer update was performed")

    changed = 0
    sd_after = model.state_dict()
    for k, v in sd_after.items():
        if k in init_snapshot and v.shape == init_snapshot[k].shape:
            if not torch.equal(v.detach().cpu(), init_snapshot[k].detach().cpu()):
                changed += 1
    if changed == 0:
        raise RuntimeError("no model weights changed after training")

    ckpt_path = os.path.join(output_dir, "checkpoint.pt")
    _save_checkpoint(ckpt_path, model, optimizer, step,
                     {"losses": losses_log, "load_info": load_info,
                      "changed_param_tensors": changed})

    model_reloaded, _ = _load_checkpoint(ckpt_path)
    sd_reloaded = model_reloaded.state_dict()
    for k in sd_after:
        if not torch.equal(sd_after[k].detach().cpu(),
                           sd_reloaded[k].detach().cpu()):
            raise RuntimeError("reload consistency failed for parameter %s" % k)

    run = {
        "task": TASK_ID,
        "variant": "debug",
        "phase": "train",
        "cuda": True,
        "device_name": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "min_size": MIN_SIZE,
        "max_size": MAX_SIZE,
        "num_classes": NUM_CLASSES,
        "class_convention": "COCO 91-id",
        "weights_spec": WEIGHTS_SPEC,
        "weights_info": load_info,
        "train_image_count": len(train_ids),
        "optimizer_steps": step,
        "changed_param_tensors": changed,
        "losses": losses_log,
        "checkpoint": os.path.basename(ckpt_path),
        "reload_consistent": True,
        "wall_seconds": time.time() - t0,
    }
    with open(os.path.join(output_dir, "run.json"), "w") as f:
        json.dump(run, f, indent=2)
    print(json.dumps({"ok": True, "optimizer_steps": step,
                      "changed_param_tensors": changed}))
    return 0


# --------------------------------------------------------------------------- #
# predict                                                                     #
# --------------------------------------------------------------------------- #

def cmd_predict(args):
    import torch

    torch = _require_cuda()
    device = torch.device("cuda")
    t0 = time.time()

    if not os.path.isfile(args.checkpoint):
        sys.stderr.write("ERROR: missing checkpoint %s\n" % args.checkpoint)
        raise SystemExit(78)

    input_dir = args.input
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    images_json = os.path.join(input_dir, "images.json")
    if not os.path.isfile(images_json):
        sys.stderr.write("ERROR: missing %s\n" % images_json)
        raise SystemExit(78)

    images_all = _load_images_json(images_json)
    model, ckpt = _load_checkpoint(args.checkpoint)
    model.to(device).eval()
    cfg = ckpt.get("model_config", {})

    from pycocotools import mask as mask_util

    instances = {"task": TASK_ID, "phase": "predict",
                 "score_threshold": SCORE_THRESH,
                 "mask_threshold": MASK_THRESH,
                 "checkpoint": os.path.abspath(args.checkpoint),
                 "images": []}
    contours = {"task": TASK_ID, "phase": "predict",
                "score_threshold": SCORE_THRESH,
                "mask_threshold": MASK_THRESH,
                "checkpoint": os.path.abspath(args.checkpoint),
                "images": []}

    total_instances = 0
    total_contours = 0

    for im_meta in images_all:
        img_id = int(im_meta["id"])
        img_path, file_name = _resolve_image_file(input_dir, img_id, im_meta)
        arr = _load_rgb_array(img_path)
        H, W = int(arr.shape[0]), int(arr.shape[1])

        img_t = torch.from_numpy(arr).permute(2, 0, 1).contiguous().float() / 255.0
        with torch.no_grad():
            out = model([img_t.to(device)])[0]

        boxes = out["boxes"].detach().cpu()
        labels = out["labels"].detach().cpu()
        scores = out["scores"].detach().cpu()
        masks = out["masks"].detach().cpu()

        keep = scores > SCORE_THRESH
        boxes = boxes[keep]; labels = labels[keep]
        scores = scores[keep]; masks = masks[keep]

        if masks.numel() and (masks.shape[-2] != H or masks.shape[-1] != W):
            import torch.nn.functional as F
            masks = F.interpolate(masks, size=(H, W), mode="bilinear",
                                  align_corners=False)

        inst_list = []
        cont_list = []
        for i in range(boxes.shape[0]):
            xyxy = boxes[i].tolist()
            label = int(labels[i].item())
            score = float(scores[i].item())
            bin_mask = (masks[i, 0].numpy() >= MASK_THRESH).astype("uint8")
            if bin_mask.sum() == 0:
                continue

            rle = mask_util.encode(
                __import__("numpy").asfortranarray(bin_mask))
            if isinstance(rle["counts"], bytes):
                rle["counts"] = rle["counts"].decode("ascii")
            area = float(mask_util.area(rle))
            bx, by, bw, bh = mask_util.toBbox(rle).tolist()

            inst_list.append({
                "instance_index": i,
                "category_id": label,
                "score": score,
                "box_xyxy": [float(xyxy[0]), float(xyxy[1]),
                             float(xyxy[2]), float(xyxy[3])],
                "bbox": [float(xyxy[0]), float(xyxy[1]),
                         float(xyxy[2] - xyxy[0]), float(xyxy[3] - xyxy[1])],
                "area": area,
                "bbox_from_rle": [float(bx), float(by), float(bw), float(bh)],
                "segmentation": {"size": [H, W], "counts": rle["counts"]},
                "image_id": img_id,
                "file_name": file_name,
            })

            polys = _extract_contours(bin_mask)
            for pi, poly in enumerate(polys):
                cont_list.append({
                    "instance_index": i,
                    "polygon_index": pi,
                    "category_id": label,
                    "score": score,
                    "image_id": img_id,
                    "file_name": file_name,
                    "area_pixels": int(bin_mask.sum()),
                    "contour": poly,
                })

        total_instances += len(inst_list)
        total_contours += len(cont_list)
        instances["images"].append({
            "image_id": img_id, "file_name": file_name,
            "height": H, "width": W,
            "instances": inst_list,
        })
        contours["images"].append({
            "image_id": img_id, "file_name": file_name,
            "height": H, "width": W,
            "contours": cont_list,
        })
        print(json.dumps({"image_id": img_id, "file_name": file_name,
                          "instances": len(inst_list),
                          "contours": len(cont_list)}), flush=True)

    with open(os.path.join(output_dir, "instances.json"), "w") as f:
        json.dump(instances, f, indent=2)
    with open(os.path.join(output_dir, "contours.json"), "w") as f:
        json.dump(contours, f, indent=2)

    run = {
        "task": TASK_ID,
        "variant": "debug",
        "phase": "predict",
        "cuda": True,
        "device_name": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "checkpoint": os.path.abspath(args.checkpoint),
        "checkpoint_step": int(ckpt.get("step", -1)),
        "model_config": cfg,
        "score_threshold": SCORE_THRESH,
        "mask_threshold": MASK_THRESH,
        "image_count": len(images_all),
        "total_instances": total_instances,
        "total_contours": total_contours,
        "outputs": {"instances": "instances.json", "contours": "contours.json"},
        "wall_seconds": time.time() - t0,
    }
    with open(os.path.join(output_dir, "run.json"), "w") as f:
        json.dump(run, f, indent=2)
    print(json.dumps({"ok": True, "images": len(images_all),
                      "instances": total_instances,
                      "contours": total_contours}))
    return 0


# --------------------------------------------------------------------------- #
# doctor                                                                      #
# --------------------------------------------------------------------------- #

def cmd_doctor(args):
    report = {"input": os.path.abspath(args.input), "items": [], "missing": []}

    def check(name, path):
        ok = os.path.exists(path)
        report["items"].append({"name": name, "path": path, "present": ok})
        if not ok:
            report["missing"].append(path)
        return ok

    input_dir = args.input
    check("train_annotations.json", os.path.join(input_dir, "train_annotations.json"))
    check("images.json", os.path.join(input_dir, "images.json"))
    check("images_dir", os.path.join(input_dir, "images"))
    check("weights_spec", WEIGHTS_SPEC)

    env = {}
    try:
        import torch
        env["torch"] = torch.__version__
        env["cuda_available"] = bool(torch.cuda.is_available())
        if env["cuda_available"]:
            env["device_name"] = torch.cuda.get_device_name(0)
        else:
            report["missing"].append("CUDA device not available")
    except Exception as e:
        env["torch_error"] = str(e)
        report["missing"].append("torch import failed: %s" % e)

    try:
        import torchvision
        env["torchvision"] = torchvision.__version__
    except Exception as e:
        env["torchvision_error"] = str(e)
        report["missing"].append("torchvision import failed: %s" % e)

    try:
        import pycocotools
        env["pycocotools"] = getattr(pycocotools, "__version__", "present")
    except Exception as e:
        env["pycocotools_error"] = str(e)
        report["missing"].append("pycocotools import failed: %s" % e)

    try:
        import numpy
        env["numpy"] = numpy.__version__
    except Exception as e:
        env["numpy_error"] = str(e)
        report["missing"].append("numpy import failed: %s" % e)

    try:
        import PIL
        env["pillow"] = getattr(PIL, "__version__", "present")
    except Exception as e:
        env["pillow_error"] = str(e)
        report["missing"].append("Pillow import failed: %s" % e)

    backends = {}
    for mod in ("cv2", "skimage"):
        try:
            m = __import__(mod)
            backends[mod] = getattr(m, "__version__", "present")
        except Exception:
            pass
    env["contour_backends"] = backends

    images_dir = os.path.join(input_dir, "images")
    if os.path.isdir(images_dir):
        try:
            files = [f for f in os.listdir(images_dir)
                     if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            env["image_file_count"] = len(files)
        except Exception as e:
            env["image_file_count_error"] = str(e)

    # weights spec / resolution (do NOT build a model)
    if os.path.isfile(WEIGHTS_SPEC):
        try:
            with open(WEIGHTS_SPEC) as f:
                spec = json.load(f)
            env["weights_spec_contents"] = spec if not isinstance(spec, str) else spec
        except Exception as e:
            env["weights_spec_error"] = str(e)
        try:
            resolved = _resolve_weights_spec()
            env["weights_resolution"] = {
                "kind": resolved["kind"],
                "path": resolved.get("path"),
                "enum": getattr(resolved.get("enum"), "name", None),
            }
        except SystemExit:
            report["missing"].append("weights unresolvable from " + WEIGHTS_SPEC)
        except Exception as e:
            report["missing"].append("weights resolution error: %s" % e)

    report["env"] = env
    report["ok"] = len(report["missing"]) == 0
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 78


# --------------------------------------------------------------------------- #
# entrypoint                                                                  #
# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "train":
        return cmd_train(args)
    if args.command == "predict":
        return cmd_predict(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
