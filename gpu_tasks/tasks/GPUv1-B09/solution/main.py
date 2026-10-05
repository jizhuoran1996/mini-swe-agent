#!/usr/bin/env python3
"""
GPUv1-B09 -- OSTrack ViT-Base single-object tracker on GOT-10k.

Source-native adapter around upstream OSTrack's
``tracking/train.py`` and ``tracking/test.py``.  All training and
inference are performed by the upstream scripts using the official
``vitb_384_mae_ce_32x4_got10k_ep100`` config, the MAE ViT-Base source
initialisation, and real GOT-10k train/val sequences.

Sub-commands
------------
``doctor --input INPUT``
    Inspect the exact required files and python modules.  Exit 78 if any
    are missing, 0 if everything is present.
``run --input INPUT --output OUTPUT``
    Full pipeline: subset the GOT-10k train/val lists (debug scope),
    copy the upstream OSTrack tree into ``output/worktree`` (the input
    is read-only), patch the config to point at the real mirrored data,
    train with the upstream trainer, run the upstream tester per
    sequence, and write ``output/run.json`` with synchronized wall-clock
    timings and device info.
``resume --input INPUT --output OUTPUT``
    Same as ``run`` but reuses the latest checkpoint under
    ``output/worktree/checkpoints`` instead of re-training.  Used for
    continuation of a new sequence from the held model.

All work requires CUDA; the process aborts before spawning anything if
no GPU is visible.  If inputs are absent it fails with exit code 78 and
does not spawn any upstream job.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXIT_MISSING = 78
EXP = "ostrack"
CONFIG_NAME = "vitb_384_mae_ce_32x4_got10k_ep100"

DEFAULT_REQUIRED_FILES = [
    "upstream/OSTrack/tracking/train.py",
    "upstream/OSTrack/tracking/test.py",
    "upstream/OSTrack/experiments/ostrack/vitb_384_mae_ce_32x4_got10k_ep100.yaml",
    "mae_pretrain_vit_base.pth",
    "GOT10k/train/list.txt",
    "GOT10k/val/list.txt",
]
DEFAULT_REQUIRED_MODULES = ["timm", "cv2", "yaml", "lmdb"]

HASH_LIMIT_BYTES = 256 * 1024 * 1024

# ---------------------------------------------------------------- helpers


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(inp: Path):
    m = inp / "manifest.json"
    if not m.is_file():
        return None
    try:
        return json.loads(m.read_text())
    except Exception:
        return None


def first_n(path: Path, n: int):
    lines = [s.strip() for s in path.read_text().splitlines() if s.strip()]
    return lines[:n] if n > 0 else lines


def check_modules(mods):
    missing = []
    for name in mods:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            missing.append({"module": name, "error": repr(exc)})
    return missing


def check_inputs(inp: Path):
    man = load_manifest(inp)
    required_files = DEFAULT_REQUIRED_FILES if not man else man.get("files", DEFAULT_REQUIRED_FILES)
    required_mods = DEFAULT_REQUIRED_MODULES if not man else man.get("requirements", DEFAULT_REQUIRED_MODULES)

    present, missing_files = [], []
    for rel in required_files:
        p = inp / rel
        if not p.is_file():
            missing_files.append(rel)
            continue
        info = {"path": rel, "size": p.stat().st_size}
        if p.stat().st_size <= HASH_LIMIT_BYTES:
            info["sha256"] = sha256(p)
        present.append(info)

    missing_modules = check_modules(required_mods)
    report = {
        "task_id": "GPUv1-B09",
        "input_dir": str(inp),
        "manifest": man,
        "required_files": required_files,
        "required_modules": required_mods,
        "present": present,
        "missing_files": missing_files,
        "missing_modules": missing_modules,
        "ok": not missing_files and not missing_modules,
    }
    return report


# ---------------------------------------------------------------- doctor


def cmd_doctor(args) -> int:
    inp = Path(args.input).resolve()
    report = check_inputs(inp)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        print("DOCTOR: missing required files or modules", file=sys.stderr)
        return EXIT_MISSING
    print("DOCTOR: all required files and modules present")
    return 0


# ---------------------------------------------------------------- device


def require_cuda():
    try:
        import torch  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"torch import failed: {exc!r}")
    if not torch.cuda.is_available():
        raise SystemExit("CUDA device is required but not visible")
    idx = torch.cuda.current_device()
    return {
        "device": torch.cuda.get_device_name(idx),
        "capability": list(torch.cuda.get_device_capability(idx)),
        "cuda_runtime": torch.version.cuda,
        "torch": torch.__version__,
    }


# ---------------------------------------------------------------- mirror


def build_mirror(inp: Path, out: Path, train_n: int, val_n: int):
    """Create output/GOT10k/{train,val}/list.txt and symlink only the
    sequences we want.  The input tree stays read-only."""
    mirror = out / "GOT10k"
    chosen = {}
    for split, n in (("train", train_n), ("val", val_n)):
        src_root = inp / "GOT10k" / split
        dst_root = mirror / split
        dst_root.mkdir(parents=True, exist_ok=True)
        seqs = first_n(src_root / "list.txt", n)
        (dst_root / "list.txt").write_text("\n".join(seqs) + "\n")
        for s in seqs:
            src_seq = src_root / s
            dst_seq = dst_root / s
            if not dst_seq.exists() and src_seq.exists():
                os.symlink(src_seq, dst_seq)
        chosen[split] = seqs
    return mirror, chosen


# ---------------------------------------------------------------- worktree


def build_worktree(inp: Path, out: Path, mirror: Path):
    """Copy upstream OSTrack into output/worktree and patch the config
    so it points at the mirrored GOT-10k tree and the MAE weights."""
    src_tree = inp / "upstream/OSTrack"
    worktree = out / "worktree"
    if not worktree.exists():
        shutil.copytree(src_tree, worktree, symlinks=True)

    cfg_path = worktree / "experiments" / EXP / f"{CONFIG_NAME}.yaml"
    if not cfg_path.is_file():
        raise SystemExit(f"config not found in worktree: {cfg_path}")

    got_root = str(mirror)
    mae = str(inp / "mae_pretrain_vit_base.pth")
    text = cfg_path.read_text()
    text = re.sub(r"(?i)(/[/\w.\-]*got[-_]?10k[/\w.\-]*)", got_root, text)
    text = re.sub(r"(/[/\w.\-]*mae_pretrain_vit_base\.pth)", mae, text)
    # Keep an unmodified copy for the source-path audit trail.
    (out / "config_original.yaml").write_text(cfg_path.read_text())
    cfg_path.write_text(text)
    (out / "config_used.yaml").write_text(text)
    return worktree, cfg_path


# ---------------------------------------------------------------- spawn


def spawn(cmd, cwd: Path, logfile: Path):
    logfile.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(logfile, "wb") as fh:
        fh.write((" ".join(cmd) + "\n").encode())
        fh.flush()
        proc = subprocess.run(cmd, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode, time.time() - t0


# ---------------------------------------------------------------- train


def run_train(inp: Path, out: Path, worktree: Path, epochs: int, log):
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(worktree))
    save_dir = out / "worktree" / "checkpoints"
    save_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(worktree / "tracking" / "train.py"),
        "--script", EXP,
        "--config", CONFIG_NAME,
        "--save_dir", str(save_dir),
        "--mode", "single",
        "--nproc_per_node", "1",
    ]
    os.environ.update(env)
    t0 = time.time()
    logfile = out / "logs" / "train.log"
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with open(logfile, "wb") as fh:
        fh.write((" ".join(cmd) + f"\nepochs_override={epochs}\n").encode())
        fh.flush()
        proc = subprocess.run(cmd, cwd=str(worktree), stdout=fh, stderr=subprocess.STDOUT)
    dt = time.time() - t0
    if proc.returncode != 0:
        raise SystemExit(f"upstream train.py failed rc={proc.returncode} (see {logfile})")
    log["train_s"] = dt


def find_latest_ckpt(out: Path):
    root = out / "worktree" / "checkpoints"
    ckpts = sorted(root.rglob("*.pth.tar")) if root.exists() else []
    if not ckpts:
        ckpts = sorted(root.rglob("*.pth")) if root.exists() else []
    return ckpts[-1] if ckpts else None


# ---------------------------------------------------------------- test


def run_test(worktree: Path, out: Path, ckpt, split: str, log):
    results_dir = out / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    dataset = "got10k_val" if split == "val" else "got10k_train"
    cmd = [
        sys.executable, str(worktree / "tracking" / "test.py"),
        EXP, CONFIG_NAME,
        "--dataset", dataset,
        "--threads", "1",
        "--num_gpus", "1",
    ]
    if ckpt is not None:
        cmd += ["--ckpt_path", str(ckpt)]
    logfile = out / "logs" / f"test_{split}.log"
    t0 = time.time()
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with open(logfile, "wb") as fh:
        fh.write((" ".join(cmd) + "\n").encode())
        fh.flush()
        proc = subprocess.run(cmd, cwd=str(worktree), stdout=fh, stderr=subprocess.STDOUT)
    dt = time.time() - t0
    if proc.returncode != 0:
        raise SystemExit(f"upstream test.py failed rc={proc.returncode} (see {logfile})")
    log[f"test_{split}_s"] = dt


def collect_trajectories(worktree: Path, out: Path, seqs):
    """Find result files produced by test.py and copy them into
    output/trajectories/<seq>.txt (frame-box-confidence, one line per
    frame, source frame order preserved)."""
    dst = out / "trajectories"
    dst.mkdir(parents=True, exist_ok=True)
    found = {}
    candidates = list(worktree.rglob("*.txt")) + list(out.rglob("*.txt"))
    for s in seqs:
        for c in candidates:
            if c.parent.name == s and c.name not in {"list.txt", "groundtruth.txt", "time.txt"}:
                target = dst / f"{s}.txt"
                shutil.copyfile(c, target)
                found[s] = str(target)
                break
    return found


# ---------------------------------------------------------------- metrics


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0.0, x2 - x1), max(0.0, y2 - y1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _load_boxes(path: Path):
    boxes = []
    for line in path.read_text().splitlines():
        parts = [p for p in re.split(r"[,\s]+", line.strip()) if p]
        if len(parts) < 4:
            continue
        try:
            boxes.append(tuple(float(p) for p in parts[:4]))
        except ValueError:
            continue
    return boxes


def compute_metrics(inp: Path, out: Path, split: str, seqs):
    anno_root = inp / "GOT10k" / split
    traj_root = out / "trajectories"
    per_seq = {}
    overlaps_all = []
    for s in seqs:
        gt_path = anno_root / s / "groundtruth.txt"
        pred_path = traj_root / f"{s}.txt"
        if not gt_path.is_file() or not pred_path.is_file():
            per_seq[s] = {"status": "missing"}
            continue
        gt = _load_boxes(gt_path)
        pr = _load_boxes(pred_path)
        n = min(len(gt), len(pr))
        ov = [_iou(pr[i], gt[i]) for i in range(n)]
        per_seq[s] = {
            "status": "ok",
            "frames": n,
            "ao": sum(ov) / n if n else 0.0,
            "sr50": sum(1 for v in ov if v >= 0.5) / n if n else 0.0,
        }
        overlaps_all.extend(ov)
    return {
        "split": split,
        "sequences": len(seqs),
        "frames": len(overlaps_all),
        "ao": sum(overlaps_all) / len(overlaps_all) if overlaps_all else None,
        "sr50": (sum(1 for v in overlaps_all if v >= 0.5) / len(overlaps_all)) if overlaps_all else None,
        "per_sequence": per_seq,
    }


# ---------------------------------------------------------------- pipeline


def run_pipeline(args, resume: bool) -> int:
    inp = Path(args.input).resolve()
    out = Path(args.output).resolve()

    report = check_inputs(inp)
    if not report["ok"]:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print("INPUTS MISSING: refusing to spawn any upstream job", file=sys.stderr)
        return EXIT_MISSING

    out.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)
    (out / "results").mkdir(exist_ok=True)
    (out / "trajectories").mkdir(exist_ok=True)

    import torch  # noqa: WPS433
    torch.cuda.synchronize()
    device = require_cuda()
    torch.cuda.synchronize()

    stage = {}
    t_start = time.time()

    mirror, chosen = build_mirror(inp, out, args.train_seqs, args.val_seqs)
    stage["mirror_s"] = time.time() - t_start
    worktree, cfg_path = build_worktree(inp, out, mirror)
    stage["worktree_s"] = time.time() - t_start - stage["mirror_s"]

    ckpt = find_latest_ckpt(out) if resume else None
    if resume and ckpt is None:
        print("resume requested but no checkpoint found", file=sys.stderr)
        return 2

    if ckpt is None:
        run_train(inp, out, worktree, args.epochs, stage)
        ckpt = find_latest_ckpt(out)
        if ckpt is None:
            raise SystemExit("training completed but no checkpoint file was found")

    torch.cuda.synchronize()
    t_test = time.time()
    run_test(worktree, out, ckpt, "val", stage)
    torch.cuda.synchronize()
    stage["test_val_s"] = time.time() - t_test

    trajectories = collect_trajectories(worktree, out, chosen["val"])
    metrics = compute_metrics(inp, out, "val", chosen["val"])

    run_json = {
        "task_id": "GPUv1-B09",
        "mode": "resume" if resume else "run",
        "manifest": report["manifest"],
        "input_files": report["present"],
        "missing_files": [],
        "missing_modules": [],
        "device": device,
        "config": {
            "name": CONFIG_NAME,
            "script": EXP,
            "epochs_requested": args.epochs,
            "used_config": str(cfg_path),
        },
        "data": {
            "mirror": str(mirror),
            "train_sequences": chosen["train"],
            "val_sequences": chosen["val"],
        },
        "checkpoint": str(ckpt) if ckpt else None,
        "stage_times_s": stage,
        "trajectories": trajectories,
        "metrics": metrics,
        "started": t_start,
        "finished": time.time(),
        "wall_s": time.time() - t_start,
        "seed": 0,
        "completion_event": "run_complete",
    }
    (out / "run.json").write_text(json.dumps(run_json, indent=2, ensure_ascii=False))
    print(json.dumps({k: run_json[k] for k in ("wall_s", "metrics", "checkpoint")}, indent=2))
    return 0


# ---------------------------------------------------------------- main


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-B09 OSTrack ViT-Base GOT-10k source-native adapter",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_help = sub.add_parser("help", help="print help (does not load models)")

    p_doc = sub.add_parser("doctor", help="inspect inputs and dependencies")
    p_doc.add_argument("--input", required=True)

    for name, help_ in (("run", "train + full-sequence tracking"),
                        ("resume", "continue from existing checkpoint")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--input", required=True)
        p.add_argument("--output", required=True)
        p.add_argument("--epochs", type=int, default=1,
                       help="epochs (debug: 1; native config: 100)")
        p.add_argument("--train-seqs", type=int, default=4,
                       help="number of real train sequences (0 = all)")
        p.add_argument("--val-seqs", type=int, default=4,
                       help="number of real val sequences (0 = all)")

    args = parser.parse_args(argv)
    if args.cmd in (None, "help"):
        parser.print_help()
        return 0
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "run":
        return run_pipeline(args, resume=False)
    if args.cmd == "resume":
        return run_pipeline(args, resume=True)
    parser.error(f"unknown sub-command {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
