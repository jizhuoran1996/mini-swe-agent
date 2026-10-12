#!/usr/bin/env python3
"""GPUv1-B06 - Native MMDetection3D CenterPoint adapter for nuScenes 3D detection.

Commands
  doctor --input INPUT
  run    --input INPUT --output OUTPUT [--epochs N] [--seed S] [--base-lr F]
  resume --input INPUT --output OUTPUT [--epochs N] [--seed S] [--base-lr F]

The adapter drives the upstream mmdetection3d tools/train.py and tools/test.py
using the frozen source config
  configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py
It never fabricates weights, never falls back to CPU, and never reports a
missing-input diagnostic as a solved task.  CUDA is required for run/resume.
"""
import argparse
import hashlib
import json
import os
import pickle
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TASK_ID = "GPUv1-B06"
UPSTREAM_DIR = "upstream/mmdetection3d"
SOURCE_CONFIG = (
    "configs/centerpoint/"
    "centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py"
)
TRAIN_TOOL = "tools/train.py"
TEST_TOOL = "tools/test.py"

DEFAULT_REQUIRED_FILES = [
    "upstream/mmdetection3d/tools/train.py",
    "upstream/mmdetection3d/configs/centerpoint/"
    "centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py",
    "nuscenes/nuscenes_infos_train.pkl",
    "nuscenes/nuscenes_infos_val.pkl",
    "nuscenes/v1.0-trainval/scene.json",
]
DEFAULT_REQUIRED_MODULES = ["mmengine", "mmcv", "mmdet3d"]
NUSCENES_CLASSES = [
    "car", "truck", "trailer", "bus", "construction_vehicle",
    "bicycle", "motorcycle", "pedestrian", "traffic_cone", "barrier",
]


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def load_manifest(root):
    p = Path(root) / "manifest.json"
    if p.is_file():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def required_lists(manifest):
    files = manifest.get("files") or DEFAULT_REQUIRED_FILES
    reqs = manifest.get("requirements") or DEFAULT_REQUIRED_MODULES
    return list(files), list(reqs)


def cuda_probe():
    info = {"available": False, "device_count": 0, "device_name": None, "reason": None}
    try:
        import torch
        info["torch"] = torch.__version__
        info["cuda_version"] = getattr(torch.version, "cuda", None)
        if torch.cuda.is_available():
            info["available"] = True
            info["device_count"] = torch.cuda.device_count()
            info["device_name"] = torch.cuda.get_device_name(0)
        else:
            info["reason"] = "torch.cuda.is_available() is False"
    except Exception as e:
        info["reason"] = f"{type(e).__name__}: {e}"
    return info


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
def cmd_doctor(args):
    root = Path(args.input).resolve()
    manifest = load_manifest(root)
    files, reqs = required_lists(manifest)
    present, missing = [], []
    for rel in files:
        p = root / rel
        if p.is_file():
            present.append({"path": rel, "size": p.stat().st_size, "sha256": sha256(p)})
        else:
            missing.append(rel)
    mod_missing, mod_ok = [], []
    for m in reqs:
        try:
            __import__(m)
            mod_ok.append(m)
        except Exception as e:
            mod_missing.append({"module": m, "error": f"{type(e).__name__}: {e}"})
    cuda = cuda_probe()
    admissible = (not missing) and (not mod_missing) and cuda["available"]
    report = {
        "task_id": TASK_ID,
        "command": "doctor",
        "input_root": str(root),
        "manifest_scale": manifest.get("scale"),
        "manifest_gate": manifest.get("gate"),
        "required_files_present": present,
        "required_files_missing": missing,
        "required_modules_present": mod_ok,
        "required_modules_missing": mod_missing,
        "cuda": cuda,
        "admissible": admissible,
        "checked_at_utc": utcnow(),
    }
    print(json.dumps(report, indent=2))
    return 0 if admissible else 78


# ---------------------------------------------------------------------------
# run / resume
# ---------------------------------------------------------------------------
def _set_first_ann_file(node, value):
    if isinstance(node, dict):
        if "ann_file" in node:
            node["ann_file"] = value
            return True
        for v in node.values():
            if _set_first_ann_file(v, value):
                return True
    elif isinstance(node, (list, tuple)):
        for v in node:
            if _set_first_ann_file(v, value):
                return True
    return False


def build_debug_config(root, out_dir, epochs, seed, base_lr):
    from mmengine.config import Config
    src = Path(root) / UPSTREAM_DIR / SOURCE_CONFIG
    cfg = Config.fromfile(str(src))
    ann_train = str(Path(root) / "nuscenes" / "nuscenes_infos_train.pkl")
    ann_val = str(Path(root) / "nuscenes" / "nuscenes_infos_val.pkl")
    data = cfg.data
    for split in ("train", "val", "test"):
        if split in data:
            _set_first_ann_file(data[split], ann_train if split == "train" else ann_val)
    try:
        data["workers_per_gpu"] = max(1, min(4, (os.cpu_count() or 2) - 1))
    except Exception:
        pass
    if "data_root" in cfg:
        cfg["data_root"] = str(Path(root) / "nuscenes") + "/"
    if "max_epochs" in cfg:
        cfg["max_epochs"] = epochs
    runner = cfg.get("runner", None)
    if isinstance(runner, dict):
        if "max_epochs" in runner:
            runner["max_epochs"] = epochs
        for sch in (runner.get("schedulers") or []):
            if isinstance(sch, dict) and "end" in sch:
                sch["end"] = epochs
    cfg["randomness"] = dict(seed=seed, deterministic=False)
    if base_lr is not None:
        opt = cfg.get("optimizer", None)
        if isinstance(opt, dict) and "lr" in opt:
            opt["lr"] = float(base_lr)
    dest = Path(out_dir) / "configs" / "centerpoint_debug.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    cfg.dump(str(dest))
    return dest


def _launch(cmd, cwd, log_path):
    with open(log_path, "ab") as fh:
        fh.write(("\n$ " + " ".join(cmd) + "\n").encode())
        fh.flush()
        return subprocess.run(cmd, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT).returncode


def _find_results(test_dir, work_dir):
    names = ("results_nusc.json", "results.json")
    cands = []
    for base in (test_dir, work_dir):
        if base and Path(base).is_dir():
            for n in names:
                cands.extend(Path(base).rglob(n))
    if cands:
        return sorted(cands, key=lambda p: p.stat().st_mtime)[-1]
    return None


def build_scene_index(root, detections_json, out_path):
    val_pkl = Path(root) / "nuscenes" / "nuscenes_infos_val.pkl"
    with open(val_pkl, "rb") as fh:
        meta = pickle.load(fh)
    infos = meta["infos"] if isinstance(meta, dict) else meta
    raw = json.loads(Path(detections_json).read_text())
    results = raw.get("results", raw)
    scenes = {}
    for info in infos:
        tok = info.get("token")
        st = info.get("scene_token") or info.get("scene_name") or "unknown"
        ts = info.get("timestamp")
        entry = {
            "sample_token": tok,
            "timestamp": ts,
            "num_detections": len(results.get(tok, []) or []),
        }
        node = scenes.setdefault(st, {"scene_token": st, "samples": []})
        node["samples"].append(entry)
    for node in scenes.values():
        node["samples"].sort(key=lambda e: (e["timestamp"] is None, e["timestamp"] or 0))
        node["num_samples"] = len(node["samples"])
    out = {
        "task_id": TASK_ID,
        "num_scenes": len(scenes),
        "num_samples": sum(n["num_samples"] for n in scenes.values()),
        "classes": NUSCENES_CLASSES,
        "scenes": scenes,
    }
    Path(out_path).write_text(json.dumps(out, indent=2))
    return out


def _write_report(out_dir, cmd_name, started_utc, started, status, reason,
                  phases, input_sha, cuda, cfg_path=None, extra=None):
    report = {
        "task_id": TASK_ID,
        "command": cmd_name,
        "status": status,
        "reason": reason,
        "started_utc": started_utc,
        "finished_utc": utcnow(),
        "wall_s": round(time.time() - started, 3),
        "phases": phases,
        "required_inputs_sha256": input_sha,
        "cuda": cuda,
    }
    if cfg_path is not None:
        report["config_path"] = str(cfg_path)
    if extra:
        report.update(extra)
    (Path(out_dir) / "run.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 1


def cmd_run(args, resume):
    root = Path(args.input).resolve()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "configs").mkdir(exist_ok=True)
    (out / "work").mkdir(exist_ok=True)
    cmd_name = "resume" if resume else "run"
    started = time.time()
    started_utc = utcnow()
    manifest = load_manifest(root)
    files, reqs = required_lists(manifest)

    missing = [f for f in files if not (root / f).is_file()]
    if missing:
        report = {
            "task_id": TASK_ID, "command": cmd_name, "status": "blocked",
            "reason": "missing_required_inputs", "missing": missing,
            "started_utc": started_utc, "finished_utc": utcnow(),
        }
        (out / "run.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return 78

    mod_missing = []
    for m in reqs:
        try:
            __import__(m)
        except Exception as e:
            mod_missing.append({"module": m, "error": f"{type(e).__name__}: {e}"})
    if mod_missing:
        report = {
            "task_id": TASK_ID, "command": cmd_name, "status": "blocked",
            "reason": "missing_required_modules", "missing_modules": mod_missing,
            "started_utc": started_utc, "finished_utc": utcnow(),
        }
        (out / "run.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return 78

    cuda = cuda_probe()
    if not cuda["available"]:
        report = {
            "task_id": TASK_ID, "command": cmd_name, "status": "blocked",
            "reason": "cuda_required", "cuda": cuda,
            "started_utc": started_utc, "finished_utc": utcnow(),
        }
        (out / "run.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return 4

    if resume and not (out / "work" / "latest.pth").is_file():
        report = {
            "task_id": TASK_ID, "command": cmd_name, "status": "blocked",
            "reason": "no_checkpoint_to_resume",
            "started_utc": started_utc, "finished_utc": utcnow(),
        }
        (out / "run.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return 78

    input_sha = {f: sha256(root / f) for f in files}
    phases = []
    cfg_path = build_debug_config(root, out, args.epochs, args.seed, args.base_lr)
    upstream_root = root / UPSTREAM_DIR

    # ---- train ----
    train_cmd = [sys.executable, TRAIN_TOOL, str(cfg_path),
                 "--work-dir", str(out / "work"), "--seed", str(args.seed)]
    if resume:
        train_cmd.append("--auto-resume")
    t0 = time.time()
    rc = _launch(train_cmd, upstream_root, out / "train.log")
    phases.append({"name": "train", "returncode": rc, "wall_s": round(time.time() - t0, 3)})
    if rc != 0:
        return _write_report(out, cmd_name, started_utc, started, "failed",
                             "train_failed", phases, input_sha, cuda, cfg_path)

    ckpt = out / "work" / f"epoch_{args.epochs}.pth"
    if not ckpt.is_file():
        cands = sorted((out / "work").glob("*.pth"), key=lambda p: p.stat().st_mtime)
        if not cands:
            return _write_report(out, cmd_name, started_utc, started, "failed",
                                 "checkpoint_missing", phases, input_sha, cuda, cfg_path)
        ckpt = cands[-1]

    # ---- test / inference ----
    test_dir = out / "test"
    test_dir.mkdir(exist_ok=True)
    base_cmd = [sys.executable, TEST_TOOL, str(cfg_path), str(ckpt),
                "--work-dir", str(test_dir)]
    t0 = time.time()
    rc = _launch(base_cmd + ["--format-only"], upstream_root, out / "test.log")
    if rc != 0:
        rc = _launch(base_cmd, upstream_root, out / "test.log")
    phases.append({"name": "test", "returncode": rc, "wall_s": round(time.time() - t0, 3)})

    res = _find_results(test_dir, out / "work")
    if res is None:
        return _write_report(out, cmd_name, started_utc, started, "failed",
                             "detections_missing", phases, input_sha, cuda, cfg_path)
    det_path = out / "detections_nusc.json"
    shutil.copyfile(res, det_path)

    # ---- scene query index ----
    t0 = time.time()
    build_scene_index(root, det_path, out / "scene_index.json")
    phases.append({"name": "index", "returncode": 0, "wall_s": round(time.time() - t0, 3)})

    report = {
        "task_id": TASK_ID,
        "command": cmd_name,
        "status": "succeeded",
        "scale": "native_debug",
        "seed": args.seed,
        "epochs": args.epochs,
        "started_utc": started_utc,
        "finished_utc": utcnow(),
        "wall_s": round(time.time() - started, 3),
        "device": "cuda",
        "device_name": cuda.get("device_name"),
        "torch": cuda.get("torch"),
        "cuda_version": cuda.get("cuda_version"),
        "input_root": str(root),
        "output_root": str(out),
        "required_inputs_sha256": input_sha,
        "config_path": str(cfg_path),
        "checkpoint_path": str(ckpt),
        "detections_json": str(det_path),
        "scene_index_json": str(out / "scene_index.json"),
        "train_log": str(out / "train.log"),
        "test_log": str(out / "test.log"),
        "phases": phases,
    }
    (out / "run.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-B06 source-native MMDetection3D CenterPoint adapter (nuScenes).",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser("doctor", help="inspect required files/modules without executing")
    p_doc.add_argument("--input", required=True)

    for name, helptext in (("run", "train CenterPoint and emit val detections"),
                           ("resume", "resume training from latest checkpoint")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--input", required=True)
        p.add_argument("--output", required=True)
        p.add_argument("--epochs", type=int, default=1)
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--base-lr", type=float, default=None)

    args = ap.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args, resume=False)
    return cmd_run(args, resume=True)


if __name__ == "__main__":
    sys.exit(main())
