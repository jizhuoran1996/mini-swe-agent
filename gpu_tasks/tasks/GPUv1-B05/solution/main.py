#!/usr/bin/env python3
"""GPUv1-B05 source-native adapter.

MLPerf Inference KiTS19 reference 3D U-Net volumetric segmentation.

Commands:
  doctor --input <dir>                 inspect inputs + dependencies (no model load)
  run    --input <dir> --output <dir>  full 3D sliding-window inference, all cases
  resume --input <dir> --output <dir>  same, skipping cases marked done in progress.json

Assets (reference_model.pt, cases.json, preprocessed/case_*.npy) come from the
read-only input/ directory of the container.  If any are absent the process
reports the missing items and exits 78; no fake inputs, no CPU fallback, no
network access.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

EXIT_MISSING = 78
PATCH = 128
OVERLAP = 0.5
NUM_CLASSES = 3
SEED = 0
TASK_ID = "GPUv1-B05"
BACKEND = "MLPerf KiTS19 reference 3D U-Net inference"


# --------------------------------------------------------------------------- #
# generic helpers
# --------------------------------------------------------------------------- #
def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def normalize_case_id(v):
    if isinstance(v, bool):
        raise ValueError("bool is not a case id")
    if isinstance(v, int):
        return v
    s = str(v)
    if s.startswith("case_"):
        s = s[5:]
    return int(s)


def extract_case_list(raw):
    """Return a list of (case_id:int, case_record:dict) from cases.json."""
    items = None
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for key in ("cases", "data", "items", "case_ids", "case_list"):
            if isinstance(raw.get(key), list):
                items = raw[key]
                break
        if items is None and raw and all(isinstance(v, dict) for v in raw.values()):
            items = [{"case_id": k, **(v or {})} for k, v in raw.items()]
    out = []
    if not items:
        return out
    for it in items:
        if isinstance(it, dict):
            cid = None
            for k in ("case_id", "case_index", "case", "id", "index", "name"):
                if k in it:
                    cid = it[k]
                    break
            if cid is None:
                continue
            try:
                out.append((normalize_case_id(cid), it))
            except Exception:
                continue
        else:
            try:
                out.append((normalize_case_id(it), {}))
            except Exception:
                continue
    # de-duplicate preserving order
    seen = set()
    dedup = []
    for cid, rec in out:
        if cid in seen:
            continue
        seen.add(cid)
        dedup.append((cid, rec))
    return dedup


def try_torch_cuda():
    info = {"torch": None, "numpy": None, "cuda": False, "device_name": None}
    try:
        import torch  # noqa: F401
        import torch as _t
        info["torch"] = _t.__version__
        try:
            info["cuda"] = bool(_t.cuda.is_available())
            if info["cuda"]:
                info["device_name"] = _t.cuda.get_device_name(0)
        except Exception as e:
            info["cuda_error"] = str(e)
    except Exception as e:
        info["torch_error"] = str(e)
    try:
        import numpy as _n
        info["numpy"] = _n.__version__
    except Exception as e:
        info["numpy_error"] = str(e)
    return info


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def doctor(input_dir: Path):
    """Return (issues:list[str], info:dict). Does not import torch.models."""
    issues = []
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        issues.append(f"missing directory: {input_dir}")
        return issues, {"input_dir": str(input_dir)}

    manifest_path = input_dir / "manifest.json"
    manifest = None
    if not manifest_path.is_file():
        issues.append("missing file: input/manifest.json")
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception as e:
            issues.append(f"unreadable input/manifest.json: {e}")

    env = try_torch_cuda()
    if env.get("torch") is None:
        issues.append(f"missing module 'torch': {env.get('torch_error')}")
    if env.get("numpy") is None:
        issues.append(f"missing module 'numpy': {env.get('numpy_error')}")
    if env.get("torch") is not None and not env.get("cuda"):
        issues.append("CUDA not available (torch.cuda.is_available() is False)")

    model_path = input_dir / "reference_model.pt"
    if not model_path.is_file():
        issues.append("missing file: input/reference_model.pt")

    cases_path = input_dir / "cases.json"
    cases = []
    if not cases_path.is_file():
        issues.append("missing file: input/cases.json")
    else:
        try:
            raw = json.loads(cases_path.read_text())
            cases = extract_case_list(raw)
            if not cases:
                issues.append("input/cases.json contains no usable case ids")
        except Exception as e:
            issues.append(f"unreadable input/cases.json: {e}")

    pre_dir = input_dir / "preprocessed"
    if not pre_dir.is_dir():
        issues.append("missing directory: input/preprocessed")
    else:
        if cases:
            for cid, _rec in cases:
                f = pre_dir / f"case_{cid:05d}.npy"
                if not f.is_file():
                    issues.append(f"missing file: input/preprocessed/case_{cid:05d}.npy")
        else:
            npys = sorted(pre_dir.glob("case_*.npy"))
            if not npys:
                issues.append("missing file: input/preprocessed/case_*.npy")

    info = {
        "input_dir": str(input_dir.resolve()),
        "manifest_present": manifest is not None,
        "case_count": len(cases),
        "case_ids": [c for c, _ in cases],
        "env": env,
    }
    return issues, info


# --------------------------------------------------------------------------- #
# sliding window inference
# --------------------------------------------------------------------------- #
def make_windows(shape, patch, overlap):
    stride = max(1, int(round(patch * (1.0 - overlap))))
    axis_starts = []
    for dim in shape:
        if dim <= patch:
            axis_starts.append([0])
        else:
            s = list(range(0, dim - patch + 1, stride))
            if s[-1] != dim - patch:
                s.append(dim - patch)
            axis_starts.append(s)
    out = []
    for x in axis_starts[0]:
        for y in axis_starts[1]:
            for z in axis_starts[2]:
                out.append((x, y, z))
    return out


def load_preprocessed_npy(np, path):
    """Load a preprocessed case volume as a float32 (X,Y,Z) tensor."""
    arr = np.load(str(path), allow_pickle=False)
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    # Channel-first (C, X, Y, Z) or channel-last (X, Y, Z, C) with C in {1,3}
    if arr.ndim == 4:
        if arr.shape[0] == 1:
            arr = arr[0]
        elif arr.shape[-1] == 1:
            arr = arr[..., 0]
        elif arr.shape[0] == 3:
            arr = arr.mean(axis=0)
        else:
            raise ValueError(f"unexpected preprocessed shape {arr.shape}")
    if arr.ndim != 3:
        raise ValueError(f"unexpected preprocessed ndim {arr.ndim} shape {arr.shape}")
    return np.ascontiguousarray(arr)


def run_volume(np, torch, model, device, vol):
    """Full 3D sliding-window inference. Returns uint8 seg of vol.shape."""
    x0, y0, z0 = vol.shape
    px, py, pz = max(x0, PATCH), max(y0, PATCH), max(z0, PATCH)
    padded = np.zeros((px, py, pz), dtype=np.float32)
    padded[:x0, :y0, :z0] = vol
    logits_sum = np.zeros((NUM_CLASSES, px, py, pz), dtype=np.float32)
    weight = np.zeros((px, py, pz), dtype=np.float32)
    for (x, y, z) in make_windows((px, py, pz), PATCH, OVERLAP):
        crop = padded[x:x + PATCH, y:y + PATCH, z:z + PATCH]
        t = torch.from_numpy(crop).unsqueeze(0).unsqueeze(0).to(device)  # (1,1,P,P,P)
        with torch.no_grad():
            out = model(t)
        if isinstance(out, (tuple, list)):
            out = out[0]
        logits = out.detach().float().cpu().numpy()[0]
        if logits.shape[0] != NUM_CLASSES:
            raise ValueError(f"model returned {logits.shape[0]} classes, expected {NUM_CLASSES}")
        logits_sum[:, x:x + PATCH, y:y + PATCH, z:z + PATCH] += logits
        weight[x:x + PATCH, y:y + PATCH, z:z + PATCH] += 1.0
    logits_sum /= np.maximum(weight[None, :, :, :], 1e-6)
    seg = np.argmax(logits_sum, axis=0).astype(np.uint8)
    return seg[:x0, :y0, :z0]


def restore_shape(np, seg, target_shape):
    if tuple(seg.shape) == tuple(target_shape):
        return seg
    xs = (np.arange(target_shape[0]) * (seg.shape[0] / target_shape[0])).astype(int)
    ys = (np.arange(target_shape[1]) * (seg.shape[1] / target_shape[1])).astype(int)
    zs = (np.arange(target_shape[2]) * (seg.shape[2] / target_shape[2])).astype(int)
    return seg[np.ix_(xs, ys, zs)]


def case_geometry(rec):
    """Pull spacing / affine / original shape from a case record, defensively."""
    spacing = rec.get("spacing") or rec.get("voxel_spacing") or rec.get("pixdim")
    if spacing is None:
        spacing = [1.0, 1.0, 1.0]
    spacing = [float(v) for v in spacing]
    shape = (rec.get("original_shape") or rec.get("shape") or rec.get("volume_shape"))
    if shape is not None:
        shape = tuple(int(v) for v in shape)
    affine = rec.get("affine")
    return spacing, shape, affine


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def do_run(input_dir: Path, output_dir: Path, resume: bool):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    t_start = time.time()

    issues, info = doctor(input_dir)
    if issues:
        for msg in issues:
            print(f"[MISSING] {msg}", file=sys.stderr)
        print(f"[doctor] {len(issues)} missing item(s); refusing to run.", file=sys.stderr)
        return EXIT_MISSING

    # real work requires CUDA
    import torch  # noqa: E402
    import numpy as np  # noqa: E402
    if not torch.cuda.is_available():
        print("[FATAL] CUDA not available; this task requires a GPU.", file=sys.stderr)
        return EXIT_MISSING
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    try:
        torch.cuda.manual_seed_all(SEED)
    except Exception:
        pass
    device = torch.device("cuda:0")

    output_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = output_dir / "masks"
    masks_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "progress.json"
    completed = {}
    if resume and progress_path.is_file():
        try:
            completed = json.loads(progress_path.read_text()).get("completed", {})
        except Exception:
            completed = {}
    completed = {int(k): v for k, v in completed.items()}

    cases_path = input_dir / "cases.json"
    raw_cases = json.loads(cases_path.read_text())
    cases = extract_case_list(raw_cases)
    if not cases:
        print("[FATAL] no cases in cases.json", file=sys.stderr)
        return EXIT_MISSING

    # load the reference TorchScript model exactly as declared
    t_model = time.time()
    model_path = input_dir / "reference_model.pt"
    model = torch.jit.load(str(model_path), map_location="cpu")
    model = model.to(device).eval()
    if hasattr(model, "half"):
        pass  # fp32 declared; do not silently switch precision
    model_load_s = time.time() - t_model
    model_sha = sha256_file(model_path)

    cases_manifest = []
    csv_rows = []
    skipped = []
    for cid, rec in cases:
        if resume and cid in completed and completed[cid].get("mask_sha256"):
            skipped.append(cid)
            continue

        pre_file = input_dir / "preprocessed" / f"case_{cid:05d}.npy"
        t_case = time.time()
        vol = load_preprocessed_npy(np, pre_file)
        logits_shape_ok = vol.ndim == 3
        seg = run_volume(np, torch, model, device, vol)

        spacing, orig_shape, affine = case_geometry(rec)
        if orig_shape is not None:
            seg = restore_shape(np, seg, orig_shape)
        final_shape = tuple(int(v) for v in seg.shape)

        uniq = sorted(int(v) for v in np.unique(seg))
        if uniq == [0]:
            print(f"[WARN] case {cid}: empty mask (all background)", file=sys.stderr)
        if uniq == [1] or uniq == [2]:
            print(f"[WARN] case {cid}: degenerate single-class mask {uniq}", file=sys.stderr)

        vox_ml = float(spacing[0] * spacing[1] * spacing[2]) / 1000.0
        kidney_vox = int((seg == 1).sum())
        tumor_vox = int((seg == 2).sum())

        mask_path = masks_dir / f"case_{cid:05d}.npy"
        np.save(str(mask_path), seg)
        mask_sha = sha256_file(mask_path)
        sidecar = {
            "case_id": cid,
            "shape": list(final_shape),
            "dtype": "uint8",
            "classes": {"0": "background", "1": "kidney", "2": "tumor"},
            "spacing_mm": spacing,
            "affine": affine if affine is not None else [[spacing[0], 0, 0, 0],
                                                         [0, spacing[1], 0, 0],
                                                         [0, 0, spacing[2], 0],
                                                         [0, 0, 0, 1]],
            "source": "case-native preprocessed volume",
            "input_preprocessed": f"preprocessed/case_{cid:05d}.npy",
            "model_sha256": model_sha,
            "patch": PATCH,
            "overlap": OVERLAP,
            "mask_sha256": mask_sha,
        }
        (masks_dir / f"case_{cid:05d}.json").write_text(json.dumps(sidecar, indent=2))

        case_time = time.time() - t_case
        completed[cid] = {
            "case_id": cid,
            "mask_sha256": mask_sha,
            "shape": list(final_shape),
            "classes_present": uniq,
            "kidney_voxels": kidney_vox,
            "tumor_voxels": tumor_vox,
            "case_time_s": case_time,
        }
        csv_rows.append({
            "case_id": cid,
            "shape_x": final_shape[0], "shape_y": final_shape[1], "shape_z": final_shape[2],
            "spacing_x": spacing[0], "spacing_y": spacing[1], "spacing_z": spacing[2],
            "kidney_voxels": kidney_vox, "tumor_voxels": tumor_vox,
            "kidney_ml": kidney_vox * vox_ml, "tumor_ml": tumor_vox * vox_ml,
            "classes_present": ";".join(str(u) for u in uniq),
            "mask_sha256": mask_sha,
        })
        cases_manifest.append({
            "case_id": cid,
            "mask_npy": f"masks/case_{cid:05d}.npy",
            "mask_json": f"masks/case_{cid:05d}.json",
            "shape": list(final_shape),
            "spacing_mm": spacing,
            "kidney_voxels": kidney_vox,
            "tumor_voxels": tumor_vox,
            "mask_sha256": mask_sha,
        })
        progress_path.write_text(json.dumps({"completed": completed}, indent=2))
        print(f"[case {cid:05d}] shape={final_shape} kidney={kidney_vox} tumor={tumor_vox} "
              f"({case_time:.1f}s)")

    # volumes CSV
    csv_path = output_dir / "volumes.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "case_id", "shape_x", "shape_y", "shape_z",
            "spacing_x", "spacing_y", "spacing_z",
            "kidney_voxels", "tumor_voxels", "kidney_ml", "tumor_ml",
            "classes_present", "mask_sha256"])
        w.writeheader()
        for row in csv_rows:
            w.writerow(row)

    # coverage manifest
    coverage = {
        "declared_case_count": len(cases),
        "processed_case_count": len(cases_manifest) + len(skipped),
        "newly_processed": [c for c, _ in cases if c not in skipped],
        "resumed_skipped": skipped,
        "cases": cases_manifest,
    }
    (output_dir / "manifest.json").write_text(json.dumps(coverage, indent=2))

    # run.json
    wall = time.time() - t_start
    run_json = {
        "task_id": TASK_ID,
        "backend": BACKEND,
        "status": "completed",
        "mode": "resume" if resume else "run",
        "seed": SEED,
        "config": {
            "patch": PATCH,
            "overlap": OVERLAP,
            "num_classes": NUM_CLASSES,
            "precision": "fp32",
            "sliding_window": "3D overlap-add normalized by coverage",
        },
        "device": {
            "cuda": True,
            "device_name": torch.cuda.get_device_name(0),
            "torch": torch.__version__,
            "numpy": np.__version__,
        },
        "inputs": {
            "manifest_sha256": sha256_file(input_dir / "manifest.json"),
            "cases_json_sha256": sha256_file(cases_path),
            "reference_model_sha256": model_sha,
            "input_dir": str(input_dir.resolve()),
        },
        "timing": {
            "wall_s": wall,
            "model_load_s": model_load_s,
        },
        "coverage": {
            "declared": len(cases),
            "done": len(completed),
            "skipped_this_session": skipped,
        },
        "env": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
        },
        "outputs": {
            "masks_dir": "masks/",
            "volumes_csv": "volumes.csv",
            "manifest": "manifest.json",
            "progress": "progress.json",
        },
        "notes": [
            "Source-native MLPerf KiTS19 reference TorchScript 3D U-Net adapter.",
            "Masks are uint8 with labels {0:background,1:kidney,2:tumor}; affine/spacing in sidecar JSON.",
            "This run is a real GPU job; no CPU fallback and no random/placeholder weights.",
        ],
    }
    (output_dir / "run.json").write_text(json.dumps(run_json, indent=2))
    print(f"[done] {len(completed)} case(s) completed in {wall:.1f}s -> {output_dir}")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    p = argparse.ArgumentParser(prog="main.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    pd = sub.add_parser("doctor", help="inspect inputs and dependencies (no model load)")
    pd.add_argument("--input", required=True, help="read-only input directory")

    pr = sub.add_parser("run", help="full 3D sliding-window inference on all cases")
    pr.add_argument("--input", required=True)
    pr.add_argument("--output", required=True)
    pr.add_argument("--resume", action="store_true", help="skip cases recorded as done")

    ps = sub.add_parser("resume", help="alias for run --resume")
    ps.add_argument("--input", required=True)
    ps.add_argument("--output", required=True)

    args = p.parse_args(argv)

    if args.cmd is None:
        p.print_help()
        return 0

    if args.cmd == "doctor":
        issues, info = doctor(Path(args.input))
        print(json.dumps(info, indent=2))
        if issues:
            for msg in issues:
                print(f"[MISSING] {msg}")
            print(f"doctor: {len(issues)} missing item(s)")
            return EXIT_MISSING
        print("doctor: all required inputs and dependencies present")
        return 0

    if args.cmd in ("run", "resume"):
        resume = (args.cmd == "resume") or bool(getattr(args, "resume", False))
        return do_run(Path(args.input), Path(args.output), resume)

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
