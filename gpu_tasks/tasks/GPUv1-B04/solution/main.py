#!/usr/bin/env python3
"""GPUv1-B04 (debug variant): CUDA fine-tune of SegFormer-B0 on a small
Cityscapes trainID debug split, saving a reloadable HF checkpoint, optimizer /
step / RNG state, held-out int32 pixel maps, and run.json.

Subcommands
-----------
train    --input input --output output
         Fine-tune /models/nvidia--segformer-b0-finetuned-cityscapes-1024-1024.
predict  --checkpoint CFG --input validation.jsonl --output NPY
doctor   --input input   (inspection only; exit 78 if anything is missing)

CUDA is mandatory for train/predict; a CPU fallback is never used.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

NUM_CLASSES = 19
IGNORE_INDEX = 255
DEFAULT_MODEL = "/models/nvidia--segformer-b0-finetuned-cityscapes-1024-1024"
SEED = 1234

# --------------------------------------------------------------------------- #
# small helpers                                                               #
# --------------------------------------------------------------------------- #


def _jsonl(path):
    recs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def _get_image_path(rec, input_dir):
    for k in ("image", "image_path", "img", "img_path", "file", "path"):
        if k in rec and rec[k]:
            return rec[k]
    raise KeyError(f"no image path key in record keys={sorted(rec.keys())}")


def _get_label_path(rec, input_dir):
    for k in ("label", "label_path", "mask", "mask_path", "gt", "gt_path"):
        if k in rec and rec[k]:
            return rec[k]
    return None


def _resolve_from(p, input_dir):
    """Resolve a stored (possibly relative) path against cwd, input_dir, or
    by stripping a leading 'input/' component."""
    p = Path(p)
    if p.is_absolute():
        return p
    cand = Path.cwd() / p
    if cand.exists():
        return cand
    cand = input_dir / p
    if cand.exists():
        return cand
    parts = p.parts
    if parts and parts[0] == "input":
        cand = input_dir / Path(*parts[1:])
        if cand.exists():
            return cand
    return input_dir / p


def _weight_hash(model):
    import torch  # noqa
    h = hashlib.sha256()
    for name, p in sorted(model.named_parameters()):
        h.update(name.encode("utf-8"))
        h.update(p.detach().to("cpu").contiguous().numpy().tobytes())
    return h.hexdigest()


def _miou_from_confusion(conf):
    ious = []
    for c in range(conf.shape[0]):
        tp = conf[c, c]
        fp = conf[:, c].sum() - tp
        fn = conf[c, :].sum() - tp
        den = tp + fp + fn
        if den == 0:
            continue
        ious.append(float(tp) / float(den))
    return float(np.mean(ious)) if ious else 0.0


# --------------------------------------------------------------------------- #
# doctor                                                                      #
# --------------------------------------------------------------------------- #


def doctor(args):
    input_dir = Path(args.input)
    missing = []

    top = ["train.jsonl", "validation.jsonl"]
    for n in top:
        if not (input_dir / n).is_file():
            missing.append(str(input_dir / n))

    model_dir = Path(args.model)
    for n in ("config.json", "preprocessor_config.json"):
        if not (model_dir / n).is_file():
            missing.append(str(model_dir / n))
    if not ((model_dir / "pytorch_model.bin").is_file()
            or (model_dir / "model.safetensors").is_file()):
        missing.append(str(model_dir / "(pytorch_model.bin|model.safetensors)"))

    for n in top:
        jp = input_dir / n
        if not jp.is_file():
            continue
        try:
            recs = _jsonl(jp)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{jp}: jsonl parse error: {exc}")
            continue
        if not recs:
            missing.append(f"{jp}: empty")
            continue
        for i, rec in enumerate(recs):
            try:
                ip = _get_image_path(rec, input_dir)
            except KeyError as exc:
                missing.append(f"{jp}[{i}]: {exc}")
                continue
            rp = _resolve_from(ip, input_dir)
            if not rp.is_file():
                missing.append(str(rp))
            lp = _get_label_path(rec, input_dir)
            if lp is not None:
                rl = _resolve_from(lp, input_dir)
                if not rl.is_file():
                    missing.append(str(rl))

    try:
        import torch  # noqa
    except Exception as exc:  # noqa: BLE001
        missing.append(f"dependency torch: {exc}")
    else:
        if not torch.cuda.is_available():
            missing.append("dependency: torch.cuda.is_available() == False")
    try:
        import transformers  # noqa
    except Exception as exc:  # noqa: BLE001
        missing.append(f"dependency transformers: {exc}")

    report = {"status": "missing" if missing else "ok",
              "input_dir": str(input_dir),
              "model_dir": str(model_dir),
              "missing": missing}
    print(json.dumps(report, indent=2))
    return 78 if missing else 0


# --------------------------------------------------------------------------- #
# shared inference helpers                                                    #
# --------------------------------------------------------------------------- #


def predict_records(model, proc, recs, input_dir, device):
    import torch
    from PIL import Image

    model.eval()
    preds = None
    H = W = None
    with torch.no_grad():
        for i, rec in enumerate(recs):
            ip = _resolve_from(_get_image_path(rec, input_dir), input_dir)
            img = Image.open(ip).convert("RGB")
            w, h = img.size
            pv = proc(images=img, do_resize=False,
                      return_tensors="pt")["pixel_values"].to(device)
            logits = model(pixel_values=pv).logits
            logits = torch.nn.functional.interpolate(
                logits, size=(h, w), mode="bilinear", align_corners=False)
            pred = logits.argmax(dim=1)[0].to(torch.int32).cpu().numpy()
            if preds is None:
                H, W = h, w
                preds = np.zeros((len(recs), H, W), dtype=np.int32)
            if (h, w) != (H, W):
                raise RuntimeError(
                    f"inconsistent image size at index {i}: {(h, w)} != {(H, W)}")
            preds[i] = pred
    if preds is None:
        raise RuntimeError("no records to predict")
    return preds, H, W


def eval_miou(model, proc, recs, input_dir, device):
    import torch
    from PIL import Image

    model.eval()
    conf = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64)
    with torch.no_grad():
        for rec in recs:
            ip = _resolve_from(_get_image_path(rec, input_dir), input_dir)
            lp = _get_label_path(rec, input_dir)
            if lp is None:
                continue
            lpath = _resolve_from(lp, input_dir)
            img = Image.open(ip).convert("RGB")
            lab = np.array(Image.open(lpath))
            if lab.ndim == 3:
                lab = lab[..., 0]
            w, h = img.size
            pv = proc(images=img, do_resize=False,
                      return_tensors="pt")["pixel_values"].to(device)
            logits = model(pixel_values=pv).logits
            logits = torch.nn.functional.interpolate(
                logits, size=(h, w), mode="bilinear", align_corners=False)
            pred = logits.argmax(dim=1)[0].cpu().numpy().astype(np.int64)
            gt = lab.astype(np.int64)
            m = gt != IGNORE_INDEX
            gt_m, pr_m = gt[m], pred[m]
            v = (gt_m >= 0) & (gt_m < NUM_CLASSES)
            gt_m, pr_m = gt_m[v], pr_m[v]
            idx = gt_m * NUM_CLASSES + pr_m
            binc = np.bincount(idx, minlength=NUM_CLASSES * NUM_CLASSES)
            conf += binc.reshape(NUM_CLASSES, NUM_CLASSES)
    return _miou_from_confusion(conf)


# --------------------------------------------------------------------------- #
# train                                                                       #
# --------------------------------------------------------------------------- #


def train(args):
    import torch
    from torch.utils.data import DataLoader, Dataset
    from PIL import Image
    from transformers import AutoImageProcessor, SegformerForSemanticSegmentation

    t0 = time.perf_counter()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is required but torch.cuda.is_available() is False",
              file=sys.stderr)
        return 1
    device = torch.device("cuda")

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir = output_dir / "checkpoint"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    train_jsonl = input_dir / "train.jsonl"
    val_jsonl = input_dir / "validation.jsonl"
    for p in (train_jsonl, val_jsonl):
        if not p.is_file():
            print(f"ERROR: missing required input {p}", file=sys.stderr)
            return 1

    train_recs = _jsonl(train_jsonl)
    val_recs = _jsonl(val_jsonl)
    if not train_recs:
        print(f"ERROR: {train_jsonl} has no records", file=sys.stderr)
        return 1

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)

    proc = AutoImageProcessor.from_pretrained(args.model)
    model = SegformerForSemanticSegmentation.from_pretrained(args.model).to(device)
    if int(model.config.num_labels) != NUM_CLASSES:
        print(f"ERROR: model num_labels={model.config.num_labels} != {NUM_CLASSES}",
              file=sys.stderr)
        return 1

    class CityscapesDS(Dataset):
        def __init__(self, recs):
            self.recs = recs

        def __len__(self):
            return len(self.recs)

        def __getitem__(self, i):
            rec = self.recs[i]
            ip = _resolve_from(_get_image_path(rec, input_dir), input_dir)
            lp = _resolve_from(_get_label_path(rec, input_dir), input_dir)
            img = Image.open(ip).convert("RGB")
            lab = np.array(Image.open(lp))
            if lab.ndim == 3:
                lab = lab[..., 0]
            pv = proc(images=img, do_resize=False,
                      return_tensors="pt")["pixel_values"][0]
            return pv, torch.from_numpy(lab.astype(np.int64))

    ds = CityscapesDS(train_recs)
    g = torch.Generator()
    g.manual_seed(args.seed)
    dl = DataLoader(ds, batch_size=args.batch_size, shuffle=True,
                    num_workers=0, generator=g)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr,
                            betas=(0.9, 0.999), weight_decay=0.01)
    crit = torch.nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)

    init_hash = _weight_hash(model)
    steps_per_epoch = len(dl)  # number of optimizer updates per full pass

    model.train()
    losses = []
    gstep = 0
    epoch_times = []
    for ep in range(args.epochs):
        t_ep = time.perf_counter()
        last_loss = None
        for pv, lab in dl:
            pv = pv.to(device, non_blocking=True)
            lab = lab.to(device, non_blocking=True)
            out = model(pixel_values=pv)
            logits = torch.nn.functional.interpolate(
                out.logits, size=lab.shape[-2:], mode="bilinear",
                align_corners=False)
            loss = crit(logits, lab)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            last_loss = float(loss.detach().cpu())
            losses.append(last_loss)
            gstep += 1
        epoch_times.append(time.perf_counter() - t_ep)
        print(f"epoch {ep + 1}/{args.epochs} steps={gstep} "
              f"loss={last_loss:.5f} time={epoch_times[-1]:.2f}s", flush=True)

    # Every train sample must have produced at least one gradient update:
    # the update count must equal (full passes over the dataset) * steps/epoch.
    expected_steps = steps_per_epoch * args.epochs
    if gstep < expected_steps:
        print(f"ERROR: fewer updates than expected ({gstep} < "
              f"{expected_steps})", file=sys.stderr)
        return 1
    if steps_per_epoch <= 0:
        print("ERROR: zero optimizer steps", file=sys.stderr)
        return 1

    final_hash = _weight_hash(model)
    weights_changed = init_hash != final_hash
    if not weights_changed:
        print("ERROR: weights did not change (no real gradient update)",
              file=sys.stderr)
        return 1

    t_train = time.perf_counter() - t0

    # --- save HF checkpoint (model + image processor) --------------------- #
    model.save_pretrained(str(ckpt_dir))
    proc.save_pretrained(str(ckpt_dir))

    # --- held-out predictions --------------------------------------------- #
    t1 = time.perf_counter()
    preds, H, W = predict_records(model, proc, val_recs, input_dir, device)
    preds = preds.astype(np.int32)
    np.save(output_dir / "predictions.npy", preds)
    t_pred = time.perf_counter() - t1

    # --- sanity mIoU on train split (labels available) -------------------- #
    t2 = time.perf_counter()
    miou_train = eval_miou(model, proc, train_recs, input_dir, device)
    t_eval = time.perf_counter() - t2

    # --- training state --------------------------------------------------- #
    state = {
        "optimizer_state_dict": opt.state_dict(),
        "model_state_dict": model.state_dict(),
        "global_step": gstep,
        "epochs": args.epochs,
        "steps_per_epoch": steps_per_epoch,
        "rng_torch": torch.get_rng_state(),
        "rng_cuda": torch.cuda.get_rng_state(),
        "rng_numpy": np.random.get_state(),
        "rng_python": random.getstate(),
        "args": {k: (str(v) if isinstance(v, Path) else v)
                 for k, v in vars(args).items()},
    }
    torch.save(state, output_dir / "training_state.pt")

    total = time.perf_counter() - t0
    run = {
        "task_id": "GPUv1-B04",
        "scale": "debug_only",
        "status": "ok",
        "model_path": str(args.model),
        "model_revision": "21b3847fae21ddee674abd31129307b6a1235bd9",
        "device": str(device),
        "cuda_name": torch.cuda.get_device_name(0),
        "seed": args.seed,
        "num_classes": NUM_CLASSES,
        "ignore_index": IGNORE_INDEX,
        "train_samples": len(train_recs),
        "heldout_samples": len(val_recs),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "optimizer": "AdamW",
        "steps_per_epoch": steps_per_epoch,
        "expected_steps": expected_steps,
        "global_steps": gstep,
        "all_samples_updated": gstep >= expected_steps,
        "initial_weight_hash": init_hash,
        "final_weight_hash": final_hash,
        "weights_changed": weights_changed,
        "train_loss_first": losses[0],
        "train_loss_last": losses[-1],
        "train_loss_mean": float(np.mean(losses)),
        "train_miou": miou_train,
        "timings_s": {
            "total": total,
            "train": t_train,
            "predict_heldout": t_pred,
            "eval_train_miou": t_eval,
            "epochs": epoch_times,
        },
        "outputs": {
            "checkpoint_dir": str(ckpt_dir),
            "training_state": str(output_dir / "training_state.pt"),
            "predictions_npy": str(output_dir / "predictions.npy"),
            "predictions_shape": list(preds.shape),
            "predictions_dtype": "int32",
        },
    }
    with open(output_dir / "run.json", "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2)

    print(json.dumps({"status": "ok", "global_steps": gstep,
                      "predictions_shape": list(preds.shape),
                      "weights_changed": weights_changed,
                      "train_miou": miou_train}, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# predict                                                                     #
# --------------------------------------------------------------------------- #


def predict(args):
    import torch
    from transformers import AutoImageProcessor, SegformerForSemanticSegmentation

    if not torch.cuda.is_available():
        print("ERROR: CUDA is required but not available", file=sys.stderr)
        return 1
    device = torch.device("cuda")

    ckpt = Path(args.checkpoint)
    if not ckpt.is_dir():
        print(f"ERROR: checkpoint dir not found: {ckpt}", file=sys.stderr)
        return 1
    inp = Path(args.input)
    if not inp.is_file():
        print(f"ERROR: input jsonl not found: {inp}", file=sys.stderr)
        return 1

    input_dir = inp.parent
    recs = _jsonl(inp)
    if not recs:
        print(f"ERROR: {inp} has no records", file=sys.stderr)
        return 1

    proc = AutoImageProcessor.from_pretrained(str(ckpt))
    model = SegformerForSemanticSegmentation.from_pretrained(str(ckpt)).to(device)
    model.eval()

    preds, H, W = predict_records(model, proc, recs, input_dir, device)
    outp = Path(args.output)
    if outp.parent and str(outp.parent) not in ("", "."):
        outp.parent.mkdir(parents=True, exist_ok=True)
    np.save(outp, preds.astype(np.int32))
    print(f"wrote {outp} shape={preds.shape} dtype=int32")
    return 0


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-B04 debug: SegFormer-B0 Cityscapes fine-tune and reuse.")
    sub = p.add_subparsers(dest="cmd")

    t = sub.add_parser("train", help="CUDA fine-tune and emit predictions/state")
    t.add_argument("--input", required=True, help="input directory")
    t.add_argument("--output", required=True, help="output directory")
    t.add_argument("--model", default=DEFAULT_MODEL)
    t.add_argument("--epochs", type=int, default=2)
    t.add_argument("--batch-size", type=int, default=2)
    t.add_argument("--lr", type=float, default=5e-6)
    t.add_argument("--seed", type=int, default=SEED)

    pr = sub.add_parser("predict", help="reload checkpoint and write int32 npy")
    pr.add_argument("--checkpoint", required=True)
    pr.add_argument("--input", required=True)
    pr.add_argument("--output", required=True)

    d = sub.add_parser("doctor",
                       help="inspect inputs/deps without running training")
    d.add_argument("--input", required=True)
    d.add_argument("--model", default=DEFAULT_MODEL)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    if args.cmd == "doctor":
        return doctor(args)
    if args.cmd == "train":
        return train(args)
    if args.cmd == "predict":
        return predict(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
