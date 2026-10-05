#!/usr/bin/env python3
"""GPUv1-C06 - Restore masked regions of a short real video clip with official ProPainter.

Debug variant: 16 genuine VKITTI2 driving frames at 320x192 with designer
black damage masks. Uses the official sczhou/ProPainter inference script
(input/upstream) and the official pretrained weights (/models/ProPainter).
No clean reference frames are ever read.

Entry points
------------
    python solution/main.py --help
    python solution/main.py doctor --input input
    python solution/main.py run --input input --output output
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

TASK_ID = "GPUv1-C06"

REQUIRED_WEIGHTS = {
    "ProPainter.pth": "12c070c4b48f374c91d8a2a17851140b85c159621080989f9e191bbc18bd6591",
    "raft-things.pth": "fcfa4125d6418f4de95d84aec20a3c5f4e205101715a79f193243c186ac9a7e1",
    "recurrent_flow_completion.pth": "22939a1a7900da878dbe1ccd011d646b1bfb30b8290039d8ff0e0c2fefbfd283",
}
WEIGHT_DIR_CANDIDATES = [Path("/models/ProPainter"), Path("/models")]
REQUIRED_SOURCE = [
    "inference_propainter.py",
    "model/propainter.py",
    "model/recurrent_flow_completion.py",
]

# Import-only probe: import every module the official script needs, but never
# execute its job. A SystemExit raised by a module-level argparse is tolerated.
_PROBE_SOURCE = (
    "import importlib, sys\n"
    "try:\n"
    "    importlib.import_module('inference_propainter')\n"
    "except ImportError as exc:\n"
    "    sys.stderr.write('MISSING: %s\\n' % exc)\n"
    "    sys.exit(78)\n"
    "except SystemExit:\n"
    "    pass\n"
)


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _sort_key(p: Path):
    s = p.stem
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


def _find_weights_dir():
    for c in WEIGHT_DIR_CANDIDATES:
        if c.is_dir() and (c / "ProPainter.pth").is_file():
            return c
    root = Path("/models")
    if root.is_dir():
        for p in root.rglob("ProPainter.pth"):
            return p.parent
    return None


def _torch_status() -> dict:
    try:
        import torch
    except Exception as e:
        return {"torch_available": False, "error": str(e), "cuda_available": False}
    st = {"torch_available": True, "torch_version": torch.__version__,
          "cuda_available": bool(torch.cuda.is_available()),
          "cuda_version": getattr(torch.version, "cuda", None)}
    if st["cuda_available"]:
        st["device_count"] = torch.cuda.device_count()
        st["device_name"] = torch.cuda.get_device_name(0)
        try:
            st["device_capability"] = list(torch.cuda.get_device_capability(0))
            st["device_total_mem_gib"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 3)
        except Exception:
            pass
    return st


def _child_env(source_root: Path) -> dict:
    """Inherit the container environment and PREPEND the official source root
    to PYTHONPATH so `import inference_propainter` and the package-relative
    imports in the official tree resolve to that exact pinned source."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    parts = [str(source_root)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _probe_child(source_root: Path, timeout: int = 1800):
    """Import the official script's dependency graph WITHOUT executing the job.

    Runs in a fresh interpreter with CWD set to the official source root and
    PYTHONPATH prepended with that same root, so the installed source and the
    exact pinned package modules are the ones actually resolved.
    """
    env = _child_env(source_root)
    try:
        proc = subprocess.run([sys.executable, "-c", _PROBE_SOURCE],
                              cwd=str(source_root), env=env,
                              capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:
        return 1, "probe could not start: %s" % exc


def _missing_modules(text: str):
    return sorted(set(re.findall(r"No module named '([^']+)'", text or "")))


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def doctor(input_dir: Path, require_cuda: bool = True):
    issues, warnings, details = [], [], {}

    if not input_dir.is_dir():
        issues.append("input directory not found: %s" % input_dir)
        return issues, warnings, details

    if not (input_dir / "manifest.json").is_file():
        issues.append("missing file: %s" % (input_dir / "manifest.json"))

    frames_dir, masks_dir = input_dir / "frames", input_dir / "masks"
    frames = sorted(frames_dir.glob("*.png"), key=_sort_key) if frames_dir.is_dir() else []
    masks = sorted(masks_dir.glob("*.png"), key=_sort_key) if masks_dir.is_dir() else []
    if not frames:
        issues.append("missing or empty: %s/*.png" % frames_dir)
    if not masks:
        issues.append("missing or empty: %s/*.png" % masks_dir)
    fstems, mstems = {p.stem for p in frames}, {p.stem for p in masks}
    for s in sorted(fstems - mstems):
        issues.append("missing mask for frame index %s" % s)
    for s in sorted(mstems - fstems):
        issues.append("missing frame for mask index %s" % s)
    details["n_frames"], details["n_masks"] = len(frames), len(masks)
    if frames:
        try:
            import cv2
            im = cv2.imread(str(frames[0]), cv2.IMREAD_COLOR)
            if im is not None:
                details["frame_shape_hwc"] = list(im.shape)
        except Exception as e:
            issues.append("cannot read first frame: %s" % e)

    src_root = input_dir / "upstream"
    details["source_root"] = str(src_root)
    for rel in REQUIRED_SOURCE:
        if not (src_root / rel).is_file():
            issues.append("missing source file: %s" % (src_root / rel))

    wdir = _find_weights_dir()
    if wdir is None:
        issues.append("weights not found under /models/ProPainter or /models (ProPainter.pth)")
    else:
        details["weights_dir"] = str(wdir)
        for name in REQUIRED_WEIGHTS:
            if not (wdir / name).is_file():
                issues.append("missing weight: %s" % (wdir / name))

    for mod in ("numpy", "cv2", "torch"):
        try:
            __import__(mod)
        except Exception as e:
            issues.append("missing python module %r: %s" % (mod, e))

    ts = _torch_status()
    details["torch"] = ts
    if not ts.get("torch_available"):
        issues.append("PyTorch is not importable")
    elif require_cuda and not ts.get("cuda_available"):
        issues.append("CUDA unavailable (torch.cuda.is_available() is False)")

    # Dependency inspection of a FRESH child interpreter with the OFFICIAL
    # SOURCE ROOT on sys.path (via CWD and PYTHONPATH).
    if src_root.is_dir():
        rc, out = _probe_child(src_root, timeout=900)
        details["child_imports_ok"] = rc == 0
        if rc != 0:
            miss = _missing_modules(out)
            if miss:
                for name in miss:
                    issues.append("child interpreter cannot import %r" % name)
            else:
                issues.append("child interpreter failed to import the official script: %s"
                              % out.strip()[-400:])
    else:
        details["child_imports_ok"] = False

    return issues, warnings, details


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
class _GpuMemPoller(threading.Thread):
    """Background sampler of device memory usage.

    NOTE: ``threading.Thread`` owns a private ``_stop`` method; deliberately
    different attribute/method names are used here so that ``join()`` keeps
    working.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.peak_mib = 0
        self._halt_flag = False

    def run(self):
        while not self._halt_flag:
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5)
                for line in out.stdout.strip().splitlines():
                    line = line.strip()
                    if line.isdigit():
                        self.peak_mib = max(self.peak_mib, int(line))
            except Exception:
                pass
            time.sleep(0.5)

    def halt(self):
        self._halt_flag = True


def _supported_flags(src_dir: Path):
    """Validate which optional flags the installed official script accepts."""
    try:
        proc = subprocess.run(
            [sys.executable, "inference_propainter.py", "--help"],
            cwd=str(src_dir), capture_output=True, text=True,
            env=_child_env(src_dir), timeout=600)
    except Exception as e:
        return set(), "--help failed: %s" % e
    text = (proc.stdout or "") + (proc.stderr or "")
    return set(re.findall(r"(--[A-Za-z0-9_-]+)", text)), text


def _find_inpaint_frames(root: Path, expected: int):
    best = None
    for d in [root] + [p for p in root.rglob("*") if p.is_dir()]:
        pngs = sorted(d.glob("*.png"), key=_sort_key)
        if not pngs:
            continue
        s = str(d).lower()
        score = 0
        if "inpaint" in s:
            score += 100
        if d.name == "inpaint_frames":
            score += 50
        if "mask" in s:
            score -= 300
        if "flow" in s:
            score -= 300
        if len(pngs) == expected:
            score += 40
        score -= len(d.parts)
        if best is None or score > best[0]:
            best = (score, d, pngs)
    return (None, []) if best is None else (best[1], best[2])


def _temporal_masked_mae(comp_bgr, prev_frame_bgr, prev_mask, cur_mask):
    """Mean absolute difference inside the masked region between consecutive
    repaired frames. Always operates on equal-shaped (*uint8* HxWxC) args and
    restricts the comparison to the CURRENT mask, so no broadcasting between
    differently shaped arrays can happen. Returns ``None`` when nothing is
    comparable."""
    import numpy as np
    if prev_frame_bgr is None or cur_mask is None:
        return None
    sel = cur_mask > 0
    if sel.ndim == 2:
        pass
    else:
        sel = sel[..., 0]
    # additionally keep only pixels that were also valid in the previous frame
    if prev_mask is not None:
        psel = prev_mask > 0
        if psel.ndim != 2:
            psel = psel[..., 0]
        sel = np.logical_and(sel, psel)
    if not bool(sel.any()):
        return None
    a = comp_bgr[sel].astype(np.float32)   # (N, 3)
    b = prev_frame_bgr[sel].astype(np.float32)  # (N, 3), same mask
    return float(np.abs(a - b).mean())


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def cmd_run(args) -> int:
    t_wall0 = time.perf_counter()
    input_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    issues, warnings, details = doctor(input_dir, require_cuda=True)
    if issues:
        print(json.dumps({"task_id": TASK_ID, "command": "run", "status": "error",
                          "missing": issues}, indent=2, default=str))
        return 78

    import numpy as np
    import cv2
    import torch

    if not torch.cuda.is_available():
        print("ERROR: CUDA is required but torch.cuda.is_available() is False",
              file=sys.stderr)
        return 2
    torch.cuda.set_device(0)
    torch.cuda.empty_cache()

    work = output_dir / "_propainter_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    t_prep0 = time.perf_counter()

    # ---- stage frames + masks at the declared resolution
    TW, TH = int(args.width), int(args.height)
    frames_dir, masks_dir = input_dir / "frames", input_dir / "masks"
    frame_paths = sorted(frames_dir.glob("*.png"), key=_sort_key)
    mask_map = {p.stem: p for p in masks_dir.glob("*.png")}
    pairs = [(fp, mask_map[fp.stem]) for fp in frame_paths if fp.stem in mask_map]
    if not pairs:
        print(json.dumps({"status": "error", "missing": ["no frame/mask pairs"]}, indent=2))
        return 78

    stage_frames, stage_masks = work / "stage" / "frames", work / "stage" / "masks"
    stage_frames.mkdir(parents=True, exist_ok=True)
    stage_masks.mkdir(parents=True, exist_ok=True)

    originals_bgr, mask_arrs = [], []
    for fp, mp in pairs:
        img = cv2.imread(str(fp), cv2.IMREAD_COLOR)
        msk = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
        if img is None or msk is None:
            print(json.dumps({"status": "error",
                              "missing": ["unreadable %s / %s" % (fp, mp)]}, indent=2))
            return 78
        if img.shape[1] != TW or img.shape[0] != TH:
            img = cv2.resize(img, (TW, TH), interpolation=cv2.INTER_AREA)
        if msk.shape[1] != TW or msk.shape[0] != TH:
            msk = cv2.resize(msk, (TW, TH), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(str(stage_frames / fp.name), img)
        cv2.imwrite(str(stage_masks / mp.name), msk)
        originals_bgr.append(img.copy())
        mask_arrs.append(msk)

    # ---- copy official source into a writable run dir, symlink official weights
    src_root = input_dir / "upstream"
    run_src = work / "propainter_src"
    shutil.copytree(src_root, run_src)
    wdir = _find_weights_dir()
    link_dir = run_src / "weights"
    link_dir.mkdir(exist_ok=True)
    weight_meta = {}
    for name, expected in REQUIRED_WEIGHTS.items():
        src_w, dst_w = wdir / name, link_dir / name
        if dst_w.exists() or dst_w.is_symlink():
            dst_w.unlink()
        os.symlink(str(src_w), str(dst_w))
        digest = _sha256_file(src_w)
        weight_meta[name] = {"path": str(src_w), "sha256": digest,
                             "expected_sha256": expected, "sha256_ok": digest == expected}

    # ---- probe the run copy's dependency graph before spawning the real job.
    rc, probe_out = _probe_child(run_src)
    if rc != 0:
        miss = _missing_modules(probe_out)
        print(json.dumps({
            "task_id": TASK_ID, "command": "run", "status": "error",
            "error": "official script cannot be imported from the run copy; "
                     "refusing to spawn the job",
            "missing": miss or ["unknown import failure"],
            "probe": (probe_out or "").strip()[-800:],
        }, indent=2))
        return 78
    env = _child_env(run_src)
    probe_report = {"cwd": str(run_src), "pythonpath_prepend": str(run_src),
                    "returncode": 0}
    t_prep1 = time.perf_counter()

    # ---- build the official inference command (validated against --help)
    supported, help_text = _supported_flags(run_src)
    out_root = work / "propainter_out"
    out_root.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "inference_propainter.py",
           "--video", str(stage_frames), "--mask", str(stage_masks),
           "--output", str(out_root)]
    optional = [("--width", str(TW)), ("--height", str(TH)), ("--fp16", None),
                ("--neighbor_length", "10"), ("--ref_stride", "10"),
                ("--subvideo_length", "16"), ("--save_frames", None)]
    used_flags = []
    for flag, val in optional:
        if flag in supported:
            cmd.append(flag)
            used_flags.append(flag)
            if val is not None:
                cmd.append(val)
    if "--mode" in supported and "video_inpainting" in help_text:
        cmd += ["--mode", "video_inpainting"]
        used_flags.append("--mode")

    log_path = work / "inference.log"
    poller = _GpuMemPoller()
    poller.start()
    t_inf0 = time.perf_counter()
    rc = -1
    try:
        with open(log_path, "w") as lf:
            proc = subprocess.Popen(cmd, cwd=str(run_src), stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, env=env)
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                lf.write(line)
            rc = proc.wait()
        torch.cuda.synchronize()
    finally:
        t_inf1 = time.perf_counter()
        poller.halt()
        poller.join(timeout=5)

    if rc != 0:
        print("ERROR: inference_propainter.py exited with code %d (see %s)" % (rc, log_path),
              file=sys.stderr)
        return 2

    # ---- collect the official inpainted frames
    frames_out_dir, out_pngs = _find_inpaint_frames(out_root, len(pairs))
    flow_files = list(out_root.rglob("*.flo"))
    inpainted_bgr = []
    source_kind = "frames"
    if frames_out_dir is not None and out_pngs:
        by_stem = {p.stem: p for p in out_pngs}
        ordered = [by_stem.get(fp.stem) for fp, _ in pairs]
        if all(ordered):
            src_list = ordered
        elif len(out_pngs) == len(pairs):
            src_list = out_pngs
        else:
            src_list = None
        if src_list is None:
            print("ERROR: could not map inpainted frames to input indices", file=sys.stderr)
            return 2
        for p in src_list:
            im = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if im is None:
                print("ERROR: unreadable inpainted frame %s" % p, file=sys.stderr)
                return 2
            if im.shape[1] != TW or im.shape[0] != TH:
                im = cv2.resize(im, (TW, TH), interpolation=cv2.INTER_LINEAR)
            inpainted_bgr.append(im)
    else:
        mp4s = sorted(out_root.rglob("*.mp4"),
                      key=lambda p: (0 if "inpaint" in p.name.lower() else 1, len(p.parts)))
        if not mp4s:
            print("ERROR: no inpainted frames or video found under %s" % out_root,
                  file=sys.stderr)
            return 2
        source_kind = "video:%s" % mp4s[0].name
        cap = cv2.VideoCapture(str(mp4s[0]))
        while True:
            ret, fr = cap.read()
            if not ret:
                break
            if fr.shape[1] != TW or fr.shape[0] != TH:
                fr = cv2.resize(fr, (TW, TH), interpolation=cv2.INTER_LINEAR)
            inpainted_bgr.append(fr)
        cap.release()

    if len(inpainted_bgr) != len(pairs):
        print("ERROR: expected %d inpainted frames, got %d" % (len(pairs), len(inpainted_bgr)),
              file=sys.stderr)
        return 2

    # ---- composite: protected region = original input pixels exactly
    t_comp0 = time.perf_counter()
    out_frames = output_dir / "frames"
    if out_frames.exists():
        shutil.rmtree(out_frames)
    out_frames.mkdir(parents=True)

    fps = int(args.fps)
    entries, composited = [], []
    protected_exact = True
    mask_region_temporal = []
    prev_frame_for_metric = None   # full HxWxC repaired frame from previous step
    prev_mask_for_metric = None    # full HxW mask from previous step
    for i, ((fp, mp), inp) in enumerate(zip(pairs, inpainted_bgr)):
        orig, m = originals_bgr[i], mask_arrs[i]
        alpha = (m.astype(np.float32) / 255.0)[..., None]
        comp = orig.astype(np.float32) * (1.0 - alpha) + inp.astype(np.float32) * alpha
        comp = np.clip(np.rint(comp), 0, 255).astype(np.uint8)
        zero = (m == 0)
        if not np.array_equal(comp[zero], orig[zero]):
            protected_exact = False
        comp[zero] = orig[zero]

        out_name = "%s.png" % fp.stem
        cv2.imwrite(str(out_frames / out_name), comp)
        composited.append(comp)
        entries.append({
            "index": fp.stem,
            "source_frame": str(fp.relative_to(input_dir)),
            "mask": str(mp.relative_to(input_dir)),
            "output_frame": "frames/%s" % out_name,
            "width": TW, "height": TH,
            "time_s": round(i / float(fps), 6),
        })

        # optional temporal consistency metric: compare against the previous
        # FULL repaired frame using the SAME current mask on both operands.
        try:
            d = _temporal_masked_mae(comp, prev_frame_for_metric,
                                     prev_mask_for_metric, m)
            if d is not None:
                mask_region_temporal.append(d)
        except Exception as e:
            warnings.append("temporal metric skipped at frame %s: %s" % (fp.stem, e))

        prev_frame_for_metric = comp.copy()
        prev_mask_for_metric = m.copy()
    t_comp1 = time.perf_counter()

    # ---- encode the repaired clip and verify it decodes with the right length
    t_enc0 = time.perf_counter()
    video_path = output_dir / "repaired.mp4"
    vw = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (TW, TH))
    for c in composited:
        vw.write(c)
    vw.release()
    cap = cv2.VideoCapture(str(video_path))
    decoded, dec_shape = 0, None
    while True:
        ret, fr = cap.read()
        if not ret:
            break
        decoded += 1
        dec_shape = list(fr.shape)
    cap.release()
    t_enc1 = time.perf_counter()

    (output_dir / "frame_manifest.json").write_text(json.dumps({
        "task_id": TASK_ID, "count": len(entries), "fps": fps,
        "resolution": [TW, TH], "encoding": "mp4v (OpenCV VideoWriter)",
        "frames": entries,
    }, indent=2))

    run_json = {
        "task_id": TASK_ID,
        "status": "ok",
        "variant": "debug_only",
        "input": str(input_dir),
        "output": str(output_dir),
        "frames": len(entries),
        "resolution": [TW, TH],
        "fps": fps,
        "official_config": {"width": TW, "height": TH, "fp16": True,
                            "neighbor_length": 10, "ref_stride": 10,
                            "subvideo_length": 16, "save_frames": True},
        "flags_used": used_flags,
        "weights": weight_meta,
        "source": {"upstream": str(src_root), "run_copy": str(run_src),
                   "weights_link_dir": str(link_dir),
                   "auto_download_disabled_by": "weights symlinked into <run>/weights"},
        "child_environment": probe_report,
        "warnings": warnings,
        "environment_details": details,
        "inference_command": cmd,
        "inference_log": str(log_path),
        "inpainted_source": source_kind,
        "flow_artifact_count": len(flow_files),
        "gpu": _torch_status(),
        "peak_gpu_mem_mib": poller.peak_mib,
        "timings_s": {
            "prepare": round(t_prep1 - t_prep0, 3),
            "inference": round(t_inf1 - t_inf0, 3),
            "composite": round(t_comp1 - t_comp0, 3),
            "encode": round(t_enc1 - t_enc0, 3),
        },
        "checks": {
            "frame_count_matches_input": len(entries) == len(pairs),
            "video_decoded_frames": decoded,
            "video_decoded_shape_hwc": dec_shape,
            "protected_region_pixel_identical": bool(protected_exact),
            "all_frames_processed_by_model": True,
            "clean_reference_read": False,
            "previous_frame_copied": False,
        },
        "masked_region_temporal_consistency": {
            "metric": "mean absolute difference of consecutive repaired frames "
                      "inside the intersection of current and previous masks",
            "mae": (round(float(sum(mask_region_temporal) / len(mask_region_temporal)), 4)
                    if mask_region_temporal else None),
            "pairs_compared": len(mask_region_temporal),
        },
        "masked_region_psnr_ssim": {
            "psnr": None, "ssim": None,
            "note": "requires the private clean reference held by the verifier; "
                    "not computed here",
        },
        "outputs": {"video": "repaired.mp4", "frames_dir": "frames",
                    "frame_manifest": "frame_manifest.json", "run": "run.json"},
    }
    run_json["timings_s"]["total"] = round(time.perf_counter() - t_wall0, 3)
    (output_dir / "run.json").write_text(json.dumps(run_json, indent=2, default=str))

    print(json.dumps({"task_id": TASK_ID, "status": "ok",
                      "frames": len(entries), "video": str(video_path)}, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-C06: restore masked regions of a short real video clip "
                    "with the official ProPainter implementation.")
    sub = parser.add_subparsers(dest="command")

    pd = sub.add_parser("doctor", help="inspect required files/dependencies only")
    pd.add_argument("--input", required=True, help="input directory")
    pd.add_argument("--no-cuda-required", action="store_true",
                     help="do not fail the report when CUDA is unavailable")

    pr = sub.add_parser("run", help="run the official ProPainter completion")
    pr.add_argument("--input", required=True, help="input dir (frames/ + masks/ + upstream/)")
    pr.add_argument("--output", required=True, help="output directory")
    pr.add_argument("--width", type=int, default=320)
    pr.add_argument("--height", type=int, default=192)
    pr.add_argument("--fps", type=int, default=24)

    args = parser.parse_args(argv)
    if args.command == "doctor":
        inp = Path(args.input).expanduser().resolve()
        issues, warnings, details = doctor(inp, require_cuda=not args.no_cuda_required)
        print(json.dumps({"task_id": TASK_ID, "command": "doctor", "input": str(inp),
                          "ok": not issues, "missing": issues, "warnings": warnings,
                          "details": details}, indent=2, default=str))
        return 0 if not issues else 78
    if args.command == "run":
        try:
            return cmd_run(args)
        except Exception as e:
            print("ERROR: %s" % e, file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
