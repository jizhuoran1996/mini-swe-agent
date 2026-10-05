#!/usr/bin/env python3
"""GPUv1-B08 -- source-native adapter around the official VideoMAE SSv2 fine-tuning run.

Subcommands
-----------
  doctor   inspect input/manifest.json files + python deps + CUDA, never loads a model
  run      real GPU fine-tune via upstream/VideoMAE/run_class_finetuning.py, then reload the
           produced checkpoint and emit per-clip multi-view probabilities for the val split
  resume   same as `run --resume` (reloads checkpoint + optimizer state)
  predict  batch clip prediction from an already trained checkpoint (new clips)

The adapter never fabricates inputs.  If any file/module declared by the manifest is absent it
prints the full missing-item report and exits 78 before spawning any upstream job.
"""

import argparse
import hashlib
import importlib
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

TASK_ID = "GPUv1-B08"
NB_CLASSES = 174

# Source recipe: scripts/ssv2/videomae_vit_base_patch16_224_.../finetune.sh
SOURCE_RECIPE = {
    "model": "vit_base_patch16_224",
    "data_set": "SSV2",
    "nb_classes": NB_CLASSES,
    "input_size": 224,
    "short_side_size": 224,
    "num_frames": 16,
    "sampling_rate": 4,
    "tubelet_size": 2,
    "epochs": 30,
    "lr": 1e-3,
    "opt_betas": [0.9, 0.999],
    "weight_decay": 0.05,
    "test_num_segment": 2,
    "test_num_crop": 3,
}

REQUIRED_FILES = [
    "upstream/VideoMAE/run_class_finetuning.py",
    "videomae_pretrained.pth",
    "ssv2/train.csv",
    "ssv2/val.csv",
    "ssv2/videos",
]
REQUIRED_MODULES = ["torch", "timm", "decord", "einops"]
EXIT_MISSING = 78
EXIT_NO_CUDA = 4
EXIT_UPSTREAM = 5


# --------------------------------------------------------------------------------------- utils
def sha256_file(path, limit=1 << 30):
    st = path.stat()
    if st.st_size > limit:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def now():
    return time.time()


# ------------------------------------------------------------------------------------ inspection
def inspect_inputs(input_dir: Path):
    rep = {
        "task_id": TASK_ID,
        "input_dir": str(input_dir),
        "manifest_path": str(input_dir / "manifest.json"),
        "manifest": None,
        "present_files": [],
        "missing_files": [],
        "present_modules": [],
        "missing_modules": [],
        "cuda": None,
        "errors": [],
    }
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.is_file():
        rep["errors"].append("missing manifest.json")
        rep["missing_files"].append("manifest.json")
        return rep
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:  # pragma: no cover
        rep["errors"].append("unreadable manifest.json: %s" % exc)
        rep["missing_files"].append("manifest.json")
        return rep
    rep["manifest"] = manifest
    req_files = manifest.get("files") or REQUIRED_FILES
    req_modules = manifest.get("requirements") or REQUIRED_MODULES

    for rel in req_files:
        p = input_dir / rel
        if p.is_dir():
            n = sum(1 for _ in p.iterdir())
            rep["present_files"].append({"path": rel, "kind": "dir", "entries": n})
            if n == 0:
                rep["missing_files"].append(rel + " (empty directory)")
        elif p.is_file():
            entry = {"path": rel, "kind": "file", "size": p.stat().st_size}
            try:
                entry["sha256"] = sha256_file(p)
            except Exception as exc:
                entry["sha256_error"] = str(exc)
            rep["present_files"].append(entry)
        else:
            rep["missing_files"].append(rel)

    for mod in req_modules:
        try:
            importlib.import_module(mod)
            rep["present_modules"].append(mod)
        except Exception as exc:
            rep["missing_modules"].append({"module": mod, "error": str(exc)})

    try:
        import torch
        avail = torch.cuda.is_available()
        info = {
            "torch": torch.__version__,
            "cuda_available": bool(avail),
            "cuda_version": torch.version.cuda,
            "device_count": torch.cuda.device_count(),
        }
        if avail:
            info["device_name"] = torch.cuda.get_device_name(0)
            info["capability"] = list(torch.cuda.get_device_capability(0))
        rep["cuda"] = info
    except Exception as exc:
        rep["cuda"] = {"cuda_available": False, "error": str(exc)}
        rep["missing_modules"].append({"module": "torch", "error": str(exc)})
    return rep


def cmd_doctor(args):
    rep = inspect_inputs(Path(args.input).resolve())
    rep["python"] = sys.version
    rep["platform"] = platform.platform()
    cuda_ok = bool(rep["cuda"] and rep["cuda"].get("cuda_available"))
    missing = bool(rep["missing_files"] or rep["missing_modules"] or not cuda_ok)
    if not cuda_ok:
        rep["missing_items"].append("CUDA device") if "missing_items" in rep else None
        rep.setdefault("missing_items", []).append("CUDA device")
    rep["verdict"] = "MISSING" if missing else "OK"
    print(json.dumps(rep, indent=2, sort_keys=True))
    if args.output:
        out = Path(args.output).resolve()
        out.mkdir(parents=True, exist_ok=True)
        (out / "doctor_report.json").write_text(json.dumps(rep, indent=2, sort_keys=True))
    return EXIT_MISSING if missing else 0


# ------------------------------------------------------------------------------------ csv utils
def _tokenize_line(raw):
    raw = raw.strip().strip('"')
    if not raw:
        return []
    for sep in (";", "\t", ","):
        if sep in raw:
            toks = raw.split(sep)
            break
    else:
        toks = raw.split()
    return [t.strip().strip('"') for t in toks if t.strip().strip('"')]


def load_ssv2_csv(path: Path, nb_classes=NB_CLASSES):
    """Return (entries, label_names).  Tolerant to the ';'/'/t'/',' separators used by SSv2."""
    entries = []
    label_names = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            toks = _tokenize_line(raw)
            if not toks:
                continue
            nums, others = [], []
            for t in toks:
                if t.isdigit() and 0 <= int(t) < nb_classes:
                    nums.append(t)
                else:
                    others.append(t)
            if not nums:
                raise ValueError("cannot locate class index in %s:%d -> %r" % (path, lineno, raw))
            idx = int(nums[0])
            text = None
            vid = None
            for t in others:
                if " " in t:
                    text = t
            for t in reversed(others):
                if " " not in t and len(t) <= 48:
                    vid = t
                    break
            if vid is None:
                vid = others[-1] if others else None
            if vid is None:
                raise ValueError("cannot locate video id in %s:%d -> %r" % (path, lineno, raw))
            if vid.endswith(".mp4"):
                vid = vid[:-4]
            entries.append((vid, idx))
            if text and idx not in label_names:
                label_names[idx] = text
    return entries, label_names


# ----------------------------------------------------------------------------------- model util
def _load_state_dict(ckpt_path):
    import torch
    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:  # older torch
        obj = torch.load(str(ckpt_path), map_location="cpu")
    if isinstance(obj, dict) and "model" in obj and isinstance(obj["model"], dict):
        sd = obj["model"]
    elif isinstance(obj, dict) and "module" in obj and isinstance(obj["module"], dict):
        sd = obj["module"]
    else:
        sd = obj
    clean = {}
    for k, v in sd.items():
        clean[k[7:] if k.startswith("module.") else k] = v
    return obj, clean


def build_model(upstream_dir: Path, nb_classes=NB_CLASSES, device="cuda"):
    """Instantiate the VideoMAE ViT-Base finetune architecture (source modeling or timm)."""
    import torch
    model = None
    try:
        sys.path.insert(0, str(upstream_dir))
        mod = importlib.import_module("models.modeling_finetune")
        factory = getattr(mod, "vit_base_patch16_224", None)
        if factory is not None:
            model = factory(
                num_classes=nb_classes,
                all_frames=SOURCE_RECIPE["num_frames"],
                tubelet_size=SOURCE_RECIPE["tubelet_size"],
                img_size=SOURCE_RECIPE["input_size"],
            )
    except Exception:
        model = None
    if model is None:
        import timm
        model = timm.create_model(
            "vit_base_patch16_224",
            pretrained=False,
            num_classes=nb_classes,
            img_size=SOURCE_RECIPE["input_size"],
            all_frames=SOURCE_RECIPE["num_frames"],
            tubelet_size=SOURCE_RECIPE["tubelet_size"],
            in_chans=3,
        )
    model.to(device)
    return model


def load_trained_model(upstream_dir, ckpt_path, nb_classes, device):
    model = build_model(upstream_dir, nb_classes, device)
    obj, sd = _load_state_dict(ckpt_path)
    missing, unexpected = model.load_state_dict(sd, strict=False)
    return model, obj, list(missing), list(unexpected)


# ----------------------------------------------------------------------------- decode / sampling
def _sample_in_range(total, start, end, num_frames, sampling_rate):
    """VideoMAE temporal sampling: uniform span of num_frames*sampling_rate, stride sampling_rate."""
    import numpy as np
    lo, hi = int(start), max(int(end), int(start) + 1)
    span_len = hi - lo
    if span_len <= 0:
        return []
    want = num_frames * sampling_rate
    if span_len > want:
        idx = np.linspace(lo, hi - 1, want).astype(int)
        idx = idx[::sampling_rate][:num_frames]
    else:
        idx = np.linspace(lo, hi - 1, num_frames).astype(int)
    return idx.tolist()


def _crops_for_view(frames_uint8, short_side=256, crop=224):
    """3 views: left / center / right, after bicubic resize of the short side."""
    import numpy as np
    import torch
    import torch.nn.functional as F
    t, h, w, c = frames_uint8.shape
    x = torch.from_numpy(np.ascontiguousarray(frames_uint8)).float().permute(0, 3, 1, 2)  # T,C,H,W
    scale = short_side / min(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    x = F.interpolate(x, size=(nh, nw), mode="bicubic", align_corners=False)
    offs = [0, (nw - crop) // 2, nw - crop]
    views = [x[:, :, max(0, (nh - crop) // 2):max(0, (nh - crop) // 2) + crop,
                o:o + crop] for o in offs]
    mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    return [((v / 255.0) - mean) / std for v in views]


def decode_multiview(video_path, num_frames, sampling_rate, test_num_segment, test_num_crop):
    """Return (list_of_views[C,T,H,W], decoded_frame_indices, degeneracy_flag)."""
    import numpy as np
    from decord import VideoReader, cpu
    vr = VideoReader(str(video_path), ctx=cpu(0))
    n = len(vr)
    if n <= 0:
        raise RuntimeError("empty video: %s" % video_path)
    views, all_idx = [], []
    seg_len = n / float(test_num_segment)
    for s in range(test_num_segment):
        lo = int(round(s * seg_len))
        hi = int(round((s + 1) * seg_len))
        idx = _sample_in_range(n, lo, hi, num_frames, sampling_rate)
        if len(idx) < num_frames:
            idx = (idx + [idx[-1]] * (num_frames - len(idx)))[:num_frames]
        arr = vr.get_batch(idx).asnumpy()
        all_idx.extend(idx)
        for v in _crops_for_view(arr)[:test_num_crop]:
            views.append(v)
    arr_all = vr.get_batch(sorted(set(all_idx))).asnumpy().astype("float32")
    if len(arr_all) > 1:
        diffs = np.abs(np.diff(arr_all, axis=0)).mean()
    else:
        diffs = 0.0
    return views, all_idx, float(diffs)


# ---------------------------------------------------------------------------------- evaluation
def evaluate_clips(model, input_dir, csv_path, device, num_frames, sampling_rate,
                   test_num_segment, test_num_crop, batch_views=6, limit=None):
    import numpy as np
    import torch
    model.eval()
    entries, label_names = load_ssv2_csv(csv_path)
    if limit:
        entries = entries[:limit]
    videos_root = input_dir / "ssv2" / "videos"
    records = []
    degenerate = []
    correct = 0
    t0 = now()
    for i, (vid, label) in enumerate(entries):
        vpath = videos_root / (vid + ".mp4")
        if not vpath.is_file():
            cands = list(videos_root.glob(vid + ".*"))
            vpath = cands[0] if cands else vpath
        if not vpath.is_file():
            raise FileNotFoundError("video not found for id %s under %s" % (vid, videos_root))
        views, frame_idx, frame_diff = decode_multiview(
            vpath, num_frames, sampling_rate, test_num_segment, test_num_crop)
        if frame_diff <= 1e-6:
            degenerate.append(vid)
        probs_sum = np.zeros(NB_CLASSES, dtype=np.float64)
        with torch.no_grad():
            for j in range(0, len(views), batch_views):
                chunk = views[j:j + batch_views]
                x = torch.stack(chunk, 0).to(device, non_blocking=True)  # B,C,T,H,W
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(x)
                p = torch.softmax(logits.float(), dim=-1).cpu().numpy()
                probs_sum += p.sum(axis=0)
        probs = probs_sum / max(1, len(views))
        probs = probs / probs.sum()
        pred = int(probs.argmax())
        top5 = np.argsort(probs)[::-1][:5].tolist()
        correct += int(pred == label)
        records.append({
            "clip_id": vid,
            "video_id": vid,
            "video_path": str(vpath.relative_to(input_dir)),
            "label": int(label),
            "pred": pred,
            "top5": [int(k) for k in top5],
            "n_views": len(views),
            "frame_indices": frame_idx,
            "frame_diff_mean": frame_diff,
            "probs": [float(x) for x in probs],
        })
        if (i + 1) % 50 == 0:
            print("[eval] %d/%d clips" % (i + 1, len(entries)), flush=True)
    report = {
        "clips": len(records),
        "views_per_clip": test_num_segment * test_num_crop,
        "accuracy": (correct / len(records)) if records else None,
        "degenerate_clips": degenerate,
        "label_names_from_csv": {str(k): v for k, v in label_names.items()},
        "elapsed_s": now() - t0,
    }
    return records, report


# ---------------------------------------------------------------------------------------- stages
def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True))


def run_upstream(input_dir: Path, out_dir: Path, args, resume_path=None):
    upstream_dir = input_dir / "upstream" / "VideoMAE"
    script = upstream_dir / "run_class_finetuning.py"
    ckpt_dir = out_dir / "ckpt"
    log_dir = out_dir / "logs"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    batch = args.batch_size
    cmd = [
        sys.executable, str(script),
        "--model", SOURCE_RECIPE["model"],
        "--data_set", SOURCE_RECIPE["data_set"],
        "--nb_classes", str(SOURCE_RECIPE["nb_classes"]),
        "--data_path", str(input_dir / "ssv2"),
        "--finetune", str(input_dir / "videomae_pretrained.pth"),
        "--output_dir", str(ckpt_dir),
        "--log_dir", str(log_dir),
        "--input_size", str(SOURCE_RECIPE["input_size"]),
        "--short_side_size", str(SOURCE_RECIPE["short_side_size"]),
        "--num_frames", str(SOURCE_RECIPE["num_frames"]),
        "--sampling_rate", str(SOURCE_RECIPE["sampling_rate"]),
        "--batch_size", str(batch),
        "--opt", "adamw",
        "--lr", str(SOURCE_RECIPE["lr"]),
        "--opt_betas", str(SOURCE_RECIPE["opt_betas"][0]), str(SOURCE_RECIPE["opt_betas"][1]),
        "--weight_decay", str(SOURCE_RECIPE["weight_decay"]),
        "--epochs", str(args.epochs),
        "--save_ckpt_freq", "1",
        "--test_num_segment", str(SOURCE_RECIPE["test_num_segment"]),
        "--test_num_crop", str(SOURCE_RECIPE["test_num_crop"]),
        "--seed", str(args.seed),
    ]
    if resume_path is not None:
        cmd += ["--resume", str(resume_path)]

    env = dict(os.environ)
    env.update({
        "RANK": "0",
        "WORLD_SIZE": "1",
        "LOCAL_RANK": "0",
        "MASTER_ADDR": "127.0.0.1",
        "MASTER_PORT": str(free_port()),
        "OMP_NUM_THREADS": "1",
        "PYTHONPATH": str(upstream_dir) + os.pathsep + env.get("PYTHONPATH", ""),
        "CUDA_VISIBLE_DEVICES": env.get("CUDA_VISIBLE_DEVICES", "0"),
    })
    log_path = log_dir / "train.log"
    t0 = now()
    with open(log_path, "w") as logf:
        proc = subprocess.Popen(cmd, cwd=str(upstream_dir), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            sys.stdout.write(line)
            logf.write(line)
        rc = proc.wait()
    return {
        "command": cmd,
        "returncode": rc,
        "elapsed_s": now() - t0,
        "log": str(log_path),
        "env": {k: env[k] for k in ("RANK", "WORLD_SIZE", "LOCAL_RANK", "MASTER_ADDR", "MASTER_PORT")},
    }


def find_last_checkpoint(out_dir: Path):
    ckpt_dir = out_dir / "ckpt"
    for name in ("checkpoint-best.pth", "checkpoint-last.pth"):
        p = ckpt_dir / name
        if p.is_file():
            return p
    numbered = sorted(ckpt_dir.glob("checkpoint-*.pth"))
    return numbered[-1] if numbered else None


def verify_param_updates(input_dir: Path, ckpt_path: Path):
    """Compare a few tensors between the pretrained encoder and the finetuned checkpoint."""
    import torch
    _, sd_pre = _load_state_dict(input_dir / "videomae_pretrained.pth")
    obj, sd_ft = _load_state_dict(ckpt_path)
    checked, max_abs = [], 0.0
    for key in list(sd_ft.keys()):
        if key.endswith("head.weight") or key.endswith("blocks.11.mlp.fc2.weight"):
            if key in sd_pre and sd_pre[key].shape == sd_ft[key].shape:
                d = (sd_pre[key].float() - sd_ft[key].float()).abs().max().item()
                checked.append({"tensor": key, "max_abs_diff": d})
                max_abs = max(max_abs, d)
    return {
        "compared": checked,
        "max_abs_diff": max_abs,
        "params_updated": bool(max_abs > 0.0),
        "has_optimizer_state": bool(isinstance(obj, dict) and obj.get("optimizer") is not None),
        "has_epoch": bool(isinstance(obj, dict) and obj.get("epoch") is not None),
        "has_args": bool(isinstance(obj, dict) and obj.get("args") is not None),
    }


def cmd_run(args, resume=False):
    t_start = now()
    input_dir = Path(args.input).resolve()
    out_dir = Path(args.output).resolve()

    rep = inspect_inputs(input_dir)
    if rep["missing_files"] or rep["missing_modules"]:
        print(json.dumps(rep, indent=2, sort_keys=True))
        print("FATAL: declared inputs are unavailable; no upstream job was spawned.", file=sys.stderr)
        return EXIT_MISSING
    import torch
    if not torch.cuda.is_available():
        print(json.dumps(rep, indent=2, sort_keys=True))
        print("FATAL: CUDA is required for GPUv1-B08 and is not available.", file=sys.stderr)
        return EXIT_NO_CUDA

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "input_report.json", rep)

    train_csv = input_dir / "ssv2" / "train.csv"
    _, label_names = load_ssv2_csv(train_csv)
    index_to_label = [label_names.get(i, "class_%03d" % i) for i in range(NB_CLASSES)]
    write_json(out_dir / "label_map.json", {
        "nb_classes": NB_CLASSES,
        "index_to_label": index_to_label,
        "label_to_index": {v: i for i, v in enumerate(index_to_label) if not v.startswith("class_")},
        "source": str(train_csv),
    })
    write_json(out_dir / "sampling_config.json", SOURCE_RECIPE)

    stage = {"start": t_start}
    resume_path = None
    if resume:
        resume_path = find_last_checkpoint(out_dir)
        if resume_path is None:
            print("FATAL: --resume requested but no checkpoint found in %s" % (out_dir / "ckpt"), file=sys.stderr)
            return EXIT_UPSTREAM

    stage["train_begin"] = now()
    up = run_upstream(input_dir, out_dir, args, resume_path=resume_path)
    stage["train_end"] = now()
    if up["returncode"] != 0:
        write_json(out_dir / "run.json", {
            "task_id": TASK_ID, "status": "failed", "upstream": up, "stages": stage,
        })
        return EXIT_UPSTREAM

    ckpt_path = find_last_checkpoint(out_dir)
    if ckpt_path is None:
        print("FATAL: upstream finished but produced no checkpoint.", file=sys.stderr)
        write_json(out_dir / "run.json", {"task_id": TASK_ID, "status": "failed", "upstream": up})
        return EXIT_UPSTREAM

    stage["verify_begin"] = now()
    param_report = verify_param_updates(input_dir, ckpt_path)
    stage["verify_end"] = now()

    stage["eval_begin"] = now()
    device = "cuda"
    model, raw_ckpt, missing, unexpected = load_trained_model(
        input_dir / "upstream" / "VideoMAE", ckpt_path, NB_CLASSES, device)
    records, val_report = evaluate_clips(
        model, input_dir, input_dir / "ssv2" / "val.csv", device,
        SOURCE_RECIPE["num_frames"], SOURCE_RECIPE["sampling_rate"],
        SOURCE_RECIPE["test_num_segment"], SOURCE_RECIPE["test_num_crop"],
        limit=args.limit)
    stage["eval_end"] = now()

    pred_path = out_dir / "val_clip_predictions.jsonl"
    with open(pred_path, "w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    val_report["checkpoint_state_keys"] = {
        "missing": missing[:20], "unexpected": unexpected[:20],
        "n_missing": len(missing), "n_unexpected": len(unexpected),
        "checkpoint_has_epoch": bool(isinstance(raw_ckpt, dict) and raw_ckpt.get("epoch") is not None),
        "checkpoint_has_optimizer": bool(isinstance(raw_ckpt, dict) and raw_ckpt.get("optimizer") is not None),
    }
    write_json(out_dir / "val_report.json", val_report)

    run_json = {
        "task_id": TASK_ID,
        "status": "completed",
        "mode": "resume" if resume else "run",
        "backend": "Official VideoMAE ViT Base SSV2 fine tuning",
        "scale": "native_debug_requires_asset_admission",
        "seed": args.seed,
        "recipe": SOURCE_RECIPE,
        "effective_epochs": args.epochs,
        "per_gpu_batch": args.batch_size,
        "world_size": 1,
        "device": {
            "name": torch.cuda.get_device_name(0),
            "capability": list(torch.cuda.get_device_capability(0)),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
        },
        "upstream": up,
        "resume_checkpoint": str(resume_path) if resume_path else None,
        "checkpoint": str(ckpt_path),
        "checkpoint_sha256": sha256_file(ckpt_path),
        "parameter_updates": param_report,
        "val": {
            "clips": val_report["clips"],
            "views_per_clip": val_report["views_per_clip"],
            "accuracy": val_report["accuracy"],
            "degenerate_clips": val_report["degenerate_clips"],
            "predictions": str(pred_path),
        },
        "stages_s": {
            "total": stage["eval_end"] - stage["start"],
            "train": stage["train_end"] - stage["train_begin"],
            "verify": stage["verify_end"] - stage["verify_begin"],
            "eval": stage["eval_end"] - stage["eval_begin"],
        },
        "completion_events": [
            "upstream_returncode_0",
            "checkpoint_saved",
            "optimizer_state_present=%s" % param_report["has_optimizer_state"],
            "params_updated=%s" % param_report["params_updated"],
            "val_predictions_written",
        ],
        "limitations": [
            "native_debug scale only: not a full 30-epoch 64-GPU reference-large run",
            "single-GPU effective batch differs from the source 8/64-GPU recipe",
        ],
    }
    write_json(out_dir / "run.json", run_json)
    print(json.dumps({"status": "completed", "checkpoint": str(ckpt_path), "val": run_json["val"]}, indent=2))
    return 0


def cmd_predict(args):
    input_dir = Path(args.input).resolve()
    out_dir = Path(args.output).resolve()
    rep = inspect_inputs(input_dir)
    if rep["missing_files"] or rep["missing_modules"]:
        print(json.dumps(rep, indent=2, sort_keys=True))
        print("FATAL: declared inputs are unavailable; nothing to predict.", file=sys.stderr)
        return EXIT_MISSING
    import torch
    if not torch.cuda.is_available():
        print("FATAL: CUDA is required.", file=sys.stderr)
        return EXIT_NO_CUDA
    ckpt = Path(args.checkpoint).resolve()
    if not ckpt.is_file():
        print("FATAL: checkpoint not found: %s" % ckpt, file=sys.stderr)
        return EXIT_MISSING
    csv_path = Path(args.csv).resolve() if args.csv else (input_dir / "ssv2" / "val.csv")
    out_dir.mkdir(parents=True, exist_ok=True)
    model, _, _, _ = load_trained_model(input_dir / "upstream" / "VideoMAE", ckpt, NB_CLASSES, "cuda")
    records, report = evaluate_clips(
        model, input_dir, csv_path, "cuda",
        SOURCE_RECIPE["num_frames"], SOURCE_RECIPE["sampling_rate"],
        SOURCE_RECIPE["test_num_segment"], SOURCE_RECIPE["test_num_crop"],
        limit=args.limit)
    pred_path = out_dir / "clip_predictions.jsonl"
    with open(pred_path, "w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    report["checkpoint"] = str(ckpt)
    report["csv"] = str(csv_path)
    write_json(out_dir / "predict_report.json", report)
    print(json.dumps({"clips": report["clips"], "accuracy": report["accuracy"], "out": str(pred_path)}, indent=2))
    return 0


# ------------------------------------------------------------------------------------------ main
def main():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-B08: source-native adapter around VideoMAE SSV2 fine-tuning (run_class_finetuning.py).",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_doc = sub.add_parser("doctor", help="inspect manifest files, python deps and CUDA; exit 78 if anything is missing")
    p_doc.add_argument("--input", required=True, help="input directory containing manifest.json")
    p_doc.add_argument("--output", default=None, help="optional directory to write doctor_report.json")

    p_run = sub.add_parser("run", help="perform the real GPU fine-tune and full val clip prediction")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--batch-size", type=int, default=16)
    p_run.add_argument("--epochs", type=int, default=SOURCE_RECIPE["epochs"])
    p_run.add_argument("--seed", type=int, default=0)
    p_run.add_argument("--limit", type=int, default=None, help="optional cap on validation clips")

    p_res = sub.add_parser("resume", help="continue from the last checkpoint in --output (reloads model+optimizer state)")
    p_res.add_argument("--input", required=True)
    p_res.add_argument("--output", required=True)
    p_res.add_argument("--batch-size", type=int, default=16)
    p_res.add_argument("--epochs", type=int, default=SOURCE_RECIPE["epochs"])
    p_res.add_argument("--seed", type=int, default=0)
    p_res.add_argument("--limit", type=int, default=None)

    p_pre = sub.add_parser("predict", help="batch clip prediction from a trained checkpoint")
    p_pre.add_argument("--input", required=True)
    p_pre.add_argument("--output", required=True)
    p_pre.add_argument("--checkpoint", required=True)
    p_pre.add_argument("--csv", default=None)
    p_pre.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "run":
        return cmd_run(args, resume=False)
    if args.cmd == "resume":
        return cmd_run(args, resume=True)
    if args.cmd == "predict":
        return cmd_predict(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
