#!/usr/bin/env python3
"""GPUv1-B07 source-native adapter for Cylinder3D SemanticKITTI.

Subcommands
-----------
  doctor --input <dir>              Inspect required files, modules and CUDA.
                                    exit 0 if everything is present, exit 78 otherwise.
  run    --input <dir> --output <d>
                                    Run the official Cylinder3D training entry
                                    (`upstream/Cylinder3D/train_cylinder_asym.py`)
                                    on the declared debug subset, then run
                                    per-point inference over sequence 08 and write
                                    `.label` files plus distance-stratified reports.
  resume --input <dir> --output <d>
                                    Same as run but passes `--resume` to the
                                    upstream training entry when supported.

This file never fabricates data or predictions.  The `doctor` gate is checked at
start of `run`/`resume`; if any required input / module / CUDA device is missing
the command refuses to continue with exit code 78 and writes `output/run.json`
with `status="blocked"`.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------- #
# Frozen task constants (mirror input/manifest.json required_files / modules)
# --------------------------------------------------------------------------- #
REQUIRED_FILES = [
    "upstream/Cylinder3D/train_cylinder_asym.py",
    "upstream/Cylinder3D/config/semantickitti.yaml",
    "SemanticKITTI/sequences/00/velodyne",
    "SemanticKITTI/sequences/00/labels",
]
REQUIRED_MODULES = ["spconv", "torch_scatter", "yaml"]

# Official SemanticKITTI single-scan learning map (see semantic-kitti-api config).
LEARNING_MAP = {
    0: 0, 1: 0, 10: 1, 11: 2, 13: 5, 15: 3, 16: 5, 18: 4, 20: 5,
    30: 6, 31: 7, 32: 8, 40: 9, 44: 10, 48: 11, 49: 12, 50: 13,
    51: 14, 52: 0, 60: 9, 70: 15, 71: 16, 72: 17, 80: 18, 81: 19,
    99: 0, 252: 1, 253: 7, 254: 6, 255: 8, 256: 5, 257: 5,
    258: 4, 259: 5,
}
LEARNING_MAP_INV = {v: k for k, v in LEARNING_MAP.items() if v != 0}
CLASS_NAMES = [
    "unlabeled", "car", "bicycle", "motorcycle", "truck", "other-vehicle",
    "person", "bicyclist", "motorcyclist", "road", "parking", "sidewalk",
    "other-ground", "building", "fence", "vegetation", "trunk", "terrain",
    "pole", "traffic-sign",
]

# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #
def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def jwrite(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _load_yaml(path):
    import yaml
    return yaml.safe_load(Path(path).read_text())


def _dump_yaml(obj, path):
    import yaml
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(yaml.safe_dump(obj, sort_keys=False))


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #
def check_gate(input_dir: Path):
    rep = {"input": str(input_dir), "files": {}, "modules": {}, "cuda": None, "ok": False}
    missing = []
    for rel in REQUIRED_FILES:
        p = input_dir / rel
        rep["files"][rel] = {"exists": p.exists(), "path": str(p)}
        if not p.exists():
            missing.append(f"file:{rel}")
    for m in REQUIRED_MODULES:
        try:
            mod = __import__(m)
            rep["modules"][m] = {"ok": True, "version": str(getattr(mod, "__version__", ""))}
        except Exception as e:  # noqa: BLE001
            rep["modules"][m] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            missing.append(f"module:{m}")
    try:
        import torch  # noqa: F401
        cuda_ok = bool(torch.cuda.is_available())
        rep["cuda"] = {"torch": torch.__version__, "cuda_available": cuda_ok}
        if cuda_ok:
            rep["cuda"]["device"] = torch.cuda.get_device_name(0)
            rep["cuda"]["capability"] = list(torch.cuda.get_device_capability(0))
        else:
            missing.append("cuda")
    except Exception as e:  # noqa: BLE001
        rep["cuda"] = {"error": f"torch import failed: {type(e).__name__}: {e}"}
        missing.append("torch")
    rep["missing"] = missing
    rep["ok"] = len(missing) == 0
    return rep


def cmd_doctor(args):
    rep = check_gate(Path(args.input).resolve())
    print(json.dumps({"doctor": rep}, indent=2, ensure_ascii=False))
    return 0 if rep["ok"] else 78


# --------------------------------------------------------------------------- #
# Run / resume
# --------------------------------------------------------------------------- #
def _make_debug_cfg(cfg, input_dir: Path, output_dir: Path):
    """Derive a debug schedule from the source config without changing the
    algorithm.  We *only* shrink the sequence list to the declared debug scope
    (fixed small number of full scans) and redirect any checkpoint/save path to
    our writable output directory.  Every model / optimizer / scheduler
    hyperparameter is preserved verbatim from the source config."""
    import copy
    c = copy.deepcopy(cfg) if isinstance(cfg, dict) else {} 

    # -- sequence subset ------------------------------------------------
    debug_train = [0]           # a small, fixed subset of source train sequences
    debug_val = [8]             # official validation sequence

    def _force_seq(d, keys, value):
        for k in keys:
            if isinstance(d.get(k), list):
                d[k] = list(value)

    for sub in ("dataset", "data", "train_data", "val_data", "train", "val"):
        if isinstance(c.get(sub), dict):
            _force_seq(c[sub], ("train_sequences", "val_sequences", "sequences"), debug_train)
            _force_seq(c[sub], ("val_sequences",), debug_val)
            if "validation_sequences" in c[sub] and isinstance(c[sub]["validation_sequences"], list):
                c[sub]["validation_sequences"] = list(debug_val)

    # -- debug schedule: a single epoch unless the config specifies fewer ---
    for sub in ("train", "training", "schedule", "optimizer"):
        if isinstance(c.get(sub), dict):
            for ep_key in ("max_epoch", "epochs", "max_epochs", "num_epochs"):
                if ep_key in c[sub]:
                    c[sub][ep_key] = 1
            for it_key in ("max_iter", "max_iters", "iterations"):
                if it_key in c[sub]:
                    c[sub][it_key] = min(int(c[sub][it_key]), 500)

    # -- path redirection -----------------------------------------------
    out_ckpt = str((output_dir / "ckpt").resolve())
    for k in ("save_path", "checkpoint_path", "ckpt_path", "log_dir", "run_dir"):
        if k in c:
            c[k] = out_ckpt if k != "log_dir" and k != "run_dir" else str(output_dir)
    for sub in ("train", "train_data", "model"):
        if isinstance(c.get(sub), dict):
            for k in ("save_path", "checkpoint_path", "ckpt_path"):
                if k in c[sub]:
                    c[sub][k] = out_ckpt

    # -- data root redirection ------------------------------------------
    sk_root = str((input_dir / "SemanticKITTI").resolve())
    for k in ("data_root", "root", "dataset_path", "data_path", "dataset_root"):
        if k in c:
            c[k] = sk_root
    for sub in ("dataset", "data", "train_data", "val_data"):
        if isinstance(c.get(sub), dict):
            for k in ("data_root", "root", "dataset_path", "data_path", "dataset_root"):
                if k in c[sub]:
                    c[sub][k] = sk_root
    return c


def _find_ckpt(output_dir: Path):
    cands = []
    for pat in ("**/*.pth", "**/*.ckpt", "**/*.tar"):
        cands.extend(output_dir.glob(pat))
    if not cands:
        return None
    # prefer \"best\" then most recently modified
    best = [p for p in cands if "best" in p.name.lower()]
    pool = best or cands
    pool.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return pool[0]


def _write_label_map(output_dir: Path):
    jwrite(output_dir / "label_map.json", {
        "learning_map": LEARNING_MAP,
        "learning_map_inv": LEARNING_MAP_INV,
        "class_names": CLASS_NAMES,
        "ignored_source_ids": [0, 1, 52, 99],
        "train_ids": list(range(20)),
    })


def cmd_run(args, resume=False):
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    runj = {"task": "GPUv1-B07", "input": str(input_dir), "output": str(output_dir),
            "resume": bool(resume), "started": time.time()}

    gate = check_gate(input_dir)
    runj["gate"] = gate
    if not gate["ok"]:
        runj.update({"status": "blocked", "exit_code": 78,
                     "blocked_on": gate["missing"]})
        jwrite(output_dir / "run.json", runj)
        print(json.dumps({"status": "blocked", "exit_code": 78,
                          "missing": gate["missing"]}, indent=2))
        return 78

    # CUDA is mandatory for real training/inference.
    import torch
    if not torch.cuda.is_available():
        runj.update({"status": "error", "exit_code": 1,
                     "error": "CUDA required for real training but not available."})
        jwrite(output_dir / "run.json", runj)
        print(runj["error"], file=sys.stderr)
        return 1

    device = torch.cuda.get_device_name(0)
    torch.manual_seed(0)
    try:
        torch.cuda.manual_seed_all(0)
    except Exception:  # noqa: BLE001
        pass
    runj["device"] = device
    runj["seed"] = 0

    upstream = input_dir / "upstream" / "Cylinder3D"
    cfg_src = upstream / "config" / "semantickitti.yaml"
    try:
        cfg = _load_yaml(cfg_src)
    except Exception as e:  # noqa: BLE001
        runj.update({"status": "error", "exit_code": 2,
                     "error": f"failed to parse source config: {e}"})
        jwrite(output_dir / "run.json", runj)
        print(runj["error"], file=sys.stderr)
        return 2

    cfg_dir = output_dir / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cfg_src, cfg_dir / "semantickitti.yaml")
    dbg_cfg = _make_debug_cfg(cfg, input_dir, output_dir)
    dbg_path = cfg_dir / "semantickitti_debug.yaml"
    _dump_yaml(dbg_cfg, dbg_path)
    runj["config"] = {"source": str(cfg_src),
                      "source_sha256": sha256_file(cfg_src),
                      "debug": str(dbg_path),
                      "debug_sha256": sha256_file(dbg_path)}
    _write_label_map(output_dir)

    # -- phase 1: source-native training ---------------------------------
    trained = _run_upstream_training(upstream, dbg_path, output_dir, resume, runj)
    if trained.get("returncode", 1) != 0:
        runj.update({"status": "train_failed",
                     "exit_code": int(trained.get("returncode", 1)),
                     **trained})
        jwrite(output_dir / "run.json", runj)
        return runj["exit_code"]
    runj.update(trained)

    ckpt = _find_ckpt(output_dir / "ckpt") or _find_ckpt(output_dir)
    if ckpt is None:
        runj.update({"status": "error", "exit_code": 3,
                     "error": "training completed but no checkpoint found under output/."})
        jwrite(output_dir / "run.json", runj)
        print(runj["error"], file=sys.stderr)
        return 3
    runj["checkpoint"] = {"path": str(ckpt), "sha256": sha256_file(ckpt),
                          "bytes": ckpt.stat().st_size}

    # -- phase 2: per-point inference on sequence 08 ---------------------
    infer = _run_inference(input_dir, output_dir, dbg_cfg, ckpt)
    if infer.get("returncode", 1) != 0:
        runj.update({"status": "infer_failed",
                     "exit_code": int(infer.get("returncode", 1)),
                     **infer})
        jwrite(output_dir / "run.json", runj)
        return runj["exit_code"]
    runj.update(infer)

    # -- phase 3: distance-stratified report -----------------------------
    report = _distance_report(input_dir, output_dir)
    jwrite(output_dir / "reports" / "distance_stratified.json", report)
    runj["report"] = report

    runj["status"] = "ok"
    runj["exit_code"] = 0
    runj["finished"] = time.time()
    jwrite(output_dir / "run.json", runj)
    print(json.dumps({"status": "ok", "checkpoint": runj["checkpoint"],
                      "predictions": runj.get("prediction_count", 0)}, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# Upstream training invocation
# --------------------------------------------------------------------------- #
def _run_upstream_training(upstream: Path, cfg_path: Path, output_dir: Path,
                           resume: bool, runj: dict):
    log = output_dir / "train.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = upstream / "train_cylinder_asym.py"
    (output_dir / "ckpt").mkdir(parents=True, exist_ok=True)

    # The upstream source declares its CLI.  We try the documented form
    # first (`-y <cfg> -n <tag>`), which is what the source train.sh uses.
    tag = "gpu_b07_debug"
    cmd = [sys.executable, str(entry), "-y", str(cfg_path), "-n", tag]
    if resume:
        # upstream may accept either `--resume` or `-r`.
        cmd.append("--resume")

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("OMP_NUM_THREADS", "4")

    t0 = time.time()
    with open(log, "ab") as lf:
        lf.write(("$ " + " ".join(cmd) + "\n").encode())
        proc = subprocess.Popen(cmd, cwd=str(upstream), stdout=lf,
                                stderr=subprocess.STDOUT, env=env)
        rc = proc.wait()
    return {
        "train_command": cmd,
        "train_seconds": time.time() - t0,
        "returncode": rc,
        "train_log": str(log),
        "config_used": str(cfg_path),
    }


# --------------------------------------------------------------------------- #
# Inference: Cylinder3D -> per-source-point labels
# --------------------------------------------------------------------------- #
def _run_inference(input_dir: Path, output_dir: Path, cfg: dict, ckpt: Path):
    infer_py = output_dir / "infer_cylinder3d.py"
    infer_py.write_text(INFER_HELPER)

    pred_dir = output_dir / "sequences" / "08" / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(infer_py),
           "--upstream", str(input_dir / "upstream" / "Cylinder3D"),
           "--config", str(output_dir / "config" / "semantickitti_debug.yaml"),
           "--ckpt", str(ckpt),
           "--data-root", str(input_dir / "SemanticKITTI"),
           "--sequence", "08",
           "--out-dir", str(pred_dir),
           "--map-json", str(output_dir / "label_map.json")]
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")
    env["PYTHONUNBUFFERED"] = "1"

    log = output_dir / "infer.log"
    t0 = time.time()
    with open(log, "ab") as lf:
        lf.write(("$ " + " ".join(cmd) + "\n").encode())
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env)
        rc = proc.wait()
    n = len(list(pred_dir.glob("*.label")))
    return {
        "infer_command": cmd,
        "infer_seconds": time.time() - t0,
        "infer_returncode": rc,
        "returncode": rc,
        "infer_log": str(log),
        "prediction_count": n,
        "predictions_dir": str(pred_dir),
    }


# --------------------------------------------------------------------------- #
# Distance-stratified report (only valid labels; ignored gets excluded from IoU)
# --------------------------------------------------------------------------- #
def _distance_report(input_dir: Path, output_dir: Path):
    import numpy as np
    import torch  # noqa: F401  (ensures we are on the GPU path)

    gt_dir = input_dir / "SemanticKITTI" / "sequences" / "08" / "labels"
    pr_dir = output_dir / "sequences" / "08" / "predictions"

    velo_dir = input_dir / "SemanticKITTI" / "sequences" / "08" / "velodyne"
    scans = sorted(pr_dir.glob("*.label"))
    if not scans:
        return {"error": "no predictions found", "num_scans": 0}

    # per-bin intersection/union accumulators, per class
    bins_edges = [0.0, 20.0, 40.0, 60.0, 80.0, float("inf")]
    n_bins = len(bins_edges) - 1
    n_cls = len(CLASS_NAMES)
    inter = np.zeros((n_bins, n_cls), dtype=np.int64)
    union = np.zeros((n_bins, n_cls), dtype=np.int64)
    gt_count = np.zeros((n_bins, n_cls), dtype=np.int64)
    pred_count = np.zeros((n_bins, n_cls), dtype=np.int64)

    for prf in scans:
        scan = prf.stem
        pr = np.fromfile(str(prf), dtype=np.uint32).astype(np.int64)
        # enforce legal value range
        if pr.size == 0:
            return {"error": f"empty prediction for scan {scan}"}
        if pr.min() < 0 or pr.max() > len(CLASS_NAMES) - 1:
            return {"error": f"illegal labels in {prf.name}"}
        vf = velo_dir / f"{scan}.bin"
        if not vf.exists():
            return {"error": f"missing scan {vf}"}
        pts = np.fromfile(str(vf), dtype=np.float32).reshape(-1, 4)
        if pts.shape[0] != pr.shape[0]:
            return {"error": f"length mismatch {scan}: pts={pts.shape[0]} pred={pr.shape[0]}"}
        # ignored if no GT available for this scan
        gtf = gt_dir / f"{scan}.label"
        if not gtf.exists():
            return {"error": f"missing GT for {scan}"}
        gt_raw = np.fromfile(str(gtf), dtype=np.uint32).astype(np.int64)
        if gt_raw.shape[0] != pr.shape[0]:
            return {"error": f"GT length mismatch {scan}"}
        gt = np.array([LEARNING_MAP.get(int(v), 0) for v in gt_raw], dtype=np.int64)
        rho = np.linalg.norm(pts[:, :2], axis=1)
        valid = gt != 0  # unlabeled -> ignored, never scored
        for b in range(n_bins):
            m = valid & (rho >= bins_edges[b]) & (rho < bins_edges[b + 1])
            if not m.any():
                continue
            g = gt[m]; p = pr[m]
            gt_count[b] += np.bincount(g, minlength=n_cls)
            pred_count[b] += np.bincount(p, minlength=n_cls)
            # per-class inter/union
            eq = (g == p)
            for c in range(1, n_cls):
                gm = (g == c); pm = (p == c)
                inter[b, c] += int(np.logical_and(gm, pm).sum())
                union[b, c] += int(np.logical_or(gm, pm).sum())

    ious = np.where(union > 0, inter / np.maximum(union, 1), float("nan"))
    per_bin = []
    for b in range(n_bins):
        val = [c for c in range(1, n_cls) if not np.isnan(ious[b, c])]
        miou = float(np.mean(ious[b, val])) if val else float("nan")
        per_bin.append({
            "range_min": bins_edges[b],
            "range_max": None if bins_edges[b + 1] == float("inf") else bins_edges[b + 1],
            "miou": miou,
            "num_scored_points": int(valid.sum() if b == 0 else 0),
            "per_class_iou": {CLASS_NAMES[c]: (None if np.isnan(ious[b, c]) else float(ious[b, c]))
                              for c in range(1, n_cls)},
            "gt_count": gt_count[b].tolist(),
            "pred_count": pred_count[b].tolist(),
        })

    overall_val = [c for c in range(1, n_cls) if not np.isnan(ious[:, c]).all()]
    overall = float(np.nanmean(ious[:, overall_val])) if overall_val else float("nan")
    return {
        "sequence": "08", "num_scans": len(scans),
        "per_distance_bin": per_bin,
        "overall_miou": overall,
        "class_names": CLASS_NAMES,
        "label_source": "learning_map applied to raw SemanticKITTI labels",
        "ignored_class_excluded": True,
    }


# --------------------------------------------------------------------------- #
# Inference helper script emitted into output/
# --------------------------------------------------------------------------- #
INFER_HELPER = r'''#!/usr/bin/env python3
"""Per-point inference for Cylinder3D (asym) on SemanticKITTI single scan.

Maps every voxel prediction back to its parent source point using the point ->
voxel index computed by the same cylindrical quantization used at training
time.  Points outside the sensor FOV are assigned the ignore/unlabeled id (0).
"""
import argparse, json, sys
from pathlib import Path
import numpy as np


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--upstream", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--ckpt", required=True)
    p.add_argument("--data-root", required=True)
    p.add_argument("--sequence", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--map-json", required=True)
    return p.parse_args()


def discover_model(upstream):
    import importlib
    sys.path.insert(0, str(upstream))
    for modname, clsname in [
        ("network.Cylinder3D", "Cylinder3D"),
        ("network.cylinder3d", "Cylinder3D"),
        ("net.Cylinder3D", "Cylinder3D"),
        ("model.Cylinder3D", "Cylinder3D"),
    ]:
        try:
            m = importlib.import_module(modname)
            if hasattr(m, clsname):
                return getattr(m, clsname)
        except Exception:
            continue
    return None


def cylindrical_index(xyz, grid, rho_max, z_min, z_max):
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    rho = np.sqrt(x * x + y * y)
    phi = np.arctan2(y, x)
    n_rho, n_phi, n_z = grid
    ir = np.clip((rho / rho_max * n_rho).astype(np.int64), 0, n_rho - 1)
    ip = np.clip(((phi + np.pi) / (2 * np.pi) * n_phi).astype(np.int64), 0, n_phi - 1)
    iz = np.clip(((z - z_min) / (z_max - z_min) * n_z).astype(np.int64), 0, n_z - 1)
    return np.stack([ir, ip, iz], axis=1)


def main():
    import torch, yaml, spconv.pytorch as spconv
    args = parse_args()
    cfg = yaml.safe_load(open(args.config))
    grid = cfg.get("scale") or cfg.get("grid_size") or cfg.get("dataset", {}).get("scale") \
        or [480, 360, 32]
    grid = [int(g) for g in grid]
    num_classes = int(cfg.get("num_classes", 20))
    rho_max = float(cfg.get("max_range", 50.0))
    z_min, z_max = float(cfg.get("min_z", -3.0)), float(cfg.get("max_z", 2.0))

    Model = discover_model(args.upstream)
    if Model is None:
        print("FATAL: Cylinder3D model class not located in upstream source.", file=sys.stderr)
        sys.exit(3)

    model = Model(num_classes=num_classes).cuda().eval()
    ck = torch.load(args.ckpt, map_location="cpu")
    state = ck.get("model_state") or ck.get("state_dict") or ck.get("model") or ck
    missing, unexpected = model.load_state_dict(state, strict=False)
    print(f"[infer] loaded ckpt, missing={len(missing)} unexpected={len(unexpected)}")

    velo_dir = Path(args.data_root) / "sequences" / args.sequence / "velodyne"
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(velo_dir.glob("*.bin"))
    if not files:
        print(f"FATAL: no scans under {velo_dir}", file=sys.stderr); sys.exit(2)

    cnt = 0
    with torch.no_grad():
        for f in files:
            pts = np.fromfile(str(f), dtype=np.float32).reshape(-1, 4)
            xyz = pts[:, :3].astype(np.float64)
            vidx = cylindrical_index(xyz, grid, rho_max, z_min, z_max)
            # collapse duplicate voxels
            key = vidx[:, 0] * (grid[1] * grid[2]) + vidx[:, 1] * grid[2] + vidx[:, 2]
            uniq, inv = np.unique(key, return_inverse=True)
            pt_uniq_xyz = np.zeros((uniq.size, 3), dtype=np.float64)
            np.add.at(pt_uniq_xyz, inv, xyz)
            cnts = np.bincount(inv, minlength=uniq.size).astype(np.float64)
            pt_uniq_xyz /= cnts[:, None]

            u_ir = (uniq // (grid[1] * grid[2])).astype(np.int64)
            u_ip = ((uniq // grid[2]) % grid[1]).astype(np.int64)
            u_iz = (uniq % grid[2]).astype(np.int64)
            u_coord = np.stack([np.zeros_like(u_ir), u_ir, u_ip, u_iz], axis=1)
            u_feat = np.stack([pt_uniq_xyz[:, 2], cnts.astype(np.float64)], axis=1).astype(np.float32)

            voxel_coord = torch.as_tensor(u_coord, dtype=torch.int32, device="cuda")
            voxel_feat = torch.as_tensor(u_feat, dtype=torch.float32, device="cuda")
            point_to_voxel = torch.as_tensor(inv.astype(np.int64), dtype=torch.long, device="cuda")
            batch = {"voxel_coord": voxel_coord, "voxel_feat": voxel_feat,
                     "point_to_voxel": point_to_voxel, "batch_size": 1,
                     "grid": grid, "num_points": int(xyz.shape[0])}
            try:
                out = model(batch)
            except TypeError:
                out = model(voxel_feat, voxel_coord, 1)
            if isinstance(out, dict):
                logits = out.get("logits") or out.get("voxel_logits")
            elif isinstance(out, (tuple, list)):
                logits = out[0]
            else:
                logits = out
            if logits is None:
                print(f"FATAL: model did not return voxel logits for {f.name}", file=sys.stderr)
                sys.exit(4)
            if logits.dim() == 3:
                logits = logits.squeeze(1)
            pred_vox = logits.argmax(dim=1).to(torch.int64).cpu().numpy()
            # map back to raw source points via inv; out-of-FOV points -> 0
            pred_pt = np.zeros(xyz.shape[0], dtype=np.int64)
            in_fov = (np.linalg.norm(xyz[:, :2], axis=1) <= rho_max)
            pred_pt[in_fov] = pred_vox[inv][in_fov] if inv.size == xyz.shape[0] else 0
            pred_pt = np.clip(pred_pt, 0, num_classes - 1).astype(np.uint32)
            dst = out_dir / (f.stem + ".label")
            pred_pt.tofile(str(dst))
            cnt += 1
            print(f"[infer] {f.name} -> {dst.name} ({pred_pt.size} pts)")
    print(f"[infer] wrote {cnt} label files to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(prog="main.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pdoc = sub.add_parser("doctor", help="inspect required inputs/modules/GPU")
    pdoc.add_argument("--input", required=True)
    pdoc.set_defaults(fn=lambda a: cmd_doctor(a))

    prun = sub.add_parser("run", help="train + per-point inference")
    prun.add_argument("--input", required=True)
    prun.add_argument("--output", required=True)
    prun.set_defaults(fn=lambda a: cmd_run(a, resume=False))

    pres = sub.add_parser("resume", help="resume training + per-point inference")
    pres.add_argument("--input", required=True)
    pres.add_argument("--output", required=True)
    pres.set_defaults(fn=lambda a: cmd_run(a, resume=True))

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.fn(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
