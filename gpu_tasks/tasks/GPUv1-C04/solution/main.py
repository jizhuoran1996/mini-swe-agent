#!/usr/bin/env python3
"""GPUv1-C04 (debug variant): text-to-video asset library generator.

Uses damo-vilab/text-to-video-ms-1.7b (TextToVideoSDPipeline) on CUDA fp16 to
produce a small clip library from an input/requests.jsonl specification list.

Subcommands
-----------
  doctor --input <dir>            : inspect inputs/deps only (never loads model)
  run    --input <dir> --output <dir> [--seed N]

Outputs (under --output):
  videos/<scene_id>.mp4           : playable H.264 clip
  frames/<scene_id>/frame_XXXX.png: decoded per-frame PNGs
  index.jsonl                     : one record per generated clip
  run.json                        : full run record (inputs, params, timings)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


MODEL_REPO = "damo-vilab/text-to-video-ms-1.7b"
MODEL_REVISION = "8227dddca75a8561bf858d604cc5dae52b954d01"
DEFAULT_MODEL_PATH = "/models/damo-vilab--text-to-video-ms-1.7b"

HEIGHT = 256
WIDTH = 256
NUM_FRAMES = 16
NUM_INFERENCE_STEPS = 12
GUIDANCE_SCALE = 7.5
FPS = 8

DEFAULT_REQUEST_SEED = 2026


# ---------------------------------------------------------------------------
# huggingface_hub compatibility shims
# ---------------------------------------------------------------------------
# The diffusers copy shipped at /opt/suite-deps expects a newer
# ``huggingface_hub`` than the runtime provides. The old hub lacks:
#   * huggingface_hub.errors.CachedRepoTreeNotFoundError  (imported by
#     diffusers/pipelines/pipeline_utils.py)
#   * huggingface_hub.get_cached_repo_tree
# We install read-only, best-effort shims *before* importing diffusers. This
# only affects cached-repo enumeration; the model is loaded from an absolute
# local path with ``local_files_only=True`` and never touches these helpers.
# ---------------------------------------------------------------------------
def _install_hf_hub_shims():
    try:
        import huggingface_hub as _hub
    except Exception:
        return

    # --- 1. errors.CachedRepoTreeNotFoundError -----------------------------
    try:
        import huggingface_hub.errors as _hub_errors
    except Exception:
        _hub_errors = None

    if _hub_errors is not None and not hasattr(
        _hub_errors, "CachedRepoTreeNotFoundError"
    ):
        class CachedRepoTreeNotFoundError(Exception):
            """Best-effort shim for a newer huggingface_hub symbol."""

        _hub_errors.CachedRepoTreeNotFoundError = (
            CachedRepoTreeNotFoundError
        )
        setattr(
            _hub, "CachedRepoTreeNotFoundError", CachedRepoTreeNotFoundError
        )

    # --- 2. top-level get_cached_repo_tree ---------------------------------
    if not hasattr(_hub, "get_cached_repo_tree"):
        def _make_repofile(file_path, size=0, blob_id=None, lfs=None):
            class _RepoFileShim:
                def __init__(self):
                    self.file_path = file_path
                    self.size = size
                    self.blob_id = blob_id
                    self.lfs = lfs

                def __repr__(self):
                    return (
                        f"RepoFile(file_path={self.file_path!r}, "
                        f"size={self.size})"
                    )

            return _RepoFileShim()

        def _get_cached_repo_tree(
            repo_id,
            *,
            repo_type=None,
            revision=None,
            cache_dir=None,
            token=None,
            local_files_only=False,
            **_kwargs,
        ):
            try:
                from huggingface_hub import scan_cache_dir
            except Exception:
                return
            try:
                info = scan_cache_dir(cache_dir=cache_dir)
            except Exception:
                return
            rt = repo_type or "model"
            for repo in getattr(info, "repos", []) or []:
                if getattr(repo, "repo_id", None) != repo_id:
                    continue
                if getattr(repo, "repo_type", None) not in (rt, None):
                    continue
                found = False
                for rev in getattr(repo, "revisions", []) or []:
                    if (
                        revision
                        and getattr(rev, "commit_hash", None) != revision
                    ):
                        continue
                    for f in getattr(rev, "files", []) or []:
                        yield _make_repofile(
                            getattr(f, "file_path", None),
                            getattr(f, "size_on_disk", 0),
                            getattr(f, "blob_path", None),
                            None,
                        )
                    found = True
                    break
                if not found:
                    return

        _hub.get_cached_repo_tree = _get_cached_repo_tree


# ---------------------------------------------------------------------------
# diffusers TextToVideoSDPipeline loader (with hub shims + retry)
# ---------------------------------------------------------------------------
def _load_text_to_video_pipeline_cls():
    _install_hf_hub_shims()
    try:
        from diffusers import TextToVideoSDPipeline
        return TextToVideoSDPipeline
    except Exception:
        # Purge partially-imported diffusers modules and retry after the shims.
        for name in list(sys.modules):
            if name == "diffusers" or name.startswith("diffusers."):
                del sys.modules[name]
        _install_hf_hub_shims()
        from diffusers import TextToVideoSDPipeline
        return TextToVideoSDPipeline


def _load_export_to_video():
    try:
        from diffusers.utils import export_to_video
        return export_to_video
    except Exception:
        from diffusers.utils.export_utils import export_to_video
        return export_to_video


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _model_path():
    return os.environ.get("T2V_MODEL_PATH", DEFAULT_MODEL_PATH)


def _load_requests(path):
    reqs = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {e}")
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{lineno}: expected JSON object")
            reqs.append(obj)
    if not reqs:
        raise ValueError(f"{path}: no requests found")
    return reqs


def _prompt_of(req):
    for k in ("prompt", "text", "caption", "scene_prompt", "description"):
        v = req.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    raise ValueError(f"request has no prompt field: {sorted(req.keys())}")


def _id_of(req, idx):
    for k in ("id", "scene_id", "request_id", "name", "clip_id"):
        v = req.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return f"scene_{idx:04d}"


def _sanitize(name):
    keep = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return keep or "scene"


def _request_seed(req, idx, base_seed):
    """Deterministic per-request seed.

    Priority:
      1. explicit --seed base => base_seed + idx
      2. request's own "seed" field => use as-is
      3. fallback DEFAULT_REQUEST_SEED + idx
    """
    if base_seed is not None:
        return int(base_seed) + idx
    for k in ("seed",):
        v = req.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
        if isinstance(v, str) and v.strip().lstrip("-+").isdigit():
            return int(v.strip())
    return DEFAULT_REQUEST_SEED + idx


# ---------------------------------------------------------------------------
# frame conversion (critical: pipeline returns float in [0,1])
# ---------------------------------------------------------------------------
def _to_uint8_image(frame):
    """Convert one pipeline frame into a PIL RGB image.

    TextToVideoSDPipeline returns HWC numpy arrays of dtype float32 with
    values in [0, 1]. Casting those directly to uint8 truncates to 0 and
    yields a black video. We therefore:
      * validate all values are finite,
      * clip to [0, 1], multiply by 255, and round to nearest,
      * cast to uint8.
    If the input already is uint8 we do NOT rescale it.
    """
    import numpy as np
    from PIL import Image

    arr = np.asarray(frame)
    if arr.ndim == 3 and arr.shape[0] in (3, 4) and arr.shape[-1] not in (3, 4):
        # CHW -> HWC (rare, but be defensive)
        arr = np.transpose(arr, (1, 2, 0))

    if arr.dtype == np.uint8:
        return Image.fromarray(arr)

    if np.issubdtype(arr.dtype, np.floating):
        if not np.isfinite(arr).all():
            raise RuntimeError("non-finite values in generated frame")
        arr = np.clip(arr, 0.0, 1.0)
        arr = np.rint(arr * 255.0).astype(np.uint8)
        return Image.fromarray(arr)

    # integer but not uint8 (e.g. uint16 in [0, 255] range or [0,1] range):
    if np.issubdtype(arr.dtype, np.integer):
        amax = int(arr.max()) if arr.size else 0
        if amax <= 1:
            arr = (arr.astype(np.float32) * 255.0)
            arr = np.rint(arr).astype(np.uint8)
        else:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        return Image.fromarray(arr)

    raise RuntimeError(f"unsupported frame dtype: {arr.dtype}")


def _extract_frames(result):
    """Return a list of PIL images from a TextToVideoSDPipeline result."""
    import numpy as np

    frames = result.frames[0]
    if isinstance(frames, np.ndarray):
        if frames.ndim == 4 and frames.shape[-1] in (3, 4):
            seq = [frames[i] for i in range(frames.shape[0])]
        else:
            raise RuntimeError(f"unexpected frame array shape: {frames.shape}")
    else:
        seq = list(frames)
    return seq


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
def cmd_doctor(args):
    missing = []

    input_dir = Path(args.input)
    req_path = input_dir / "requests.jsonl"
    man_path = input_dir / "manifest.json"

    if not input_dir.exists():
        missing.append(f"input directory not found: {input_dir}")
    else:
        if not req_path.is_file():
            missing.append(f"missing input file: {req_path}")
        else:
            try:
                _load_requests(req_path)
            except Exception as e:
                missing.append(f"invalid {req_path}: {e}")
        if not man_path.is_file():
            missing.append(f"missing input file: {man_path}")

    model_path = _model_path()
    model_p = Path(model_path)
    if not model_p.is_dir():
        missing.append(f"missing model directory: {model_path}")
    elif not (model_p / "model_index.json").is_file():
        missing.append(f"missing model_index.json in {model_path}")

    try:
        import torch
    except Exception as e:
        missing.append(f"import torch failed: {e}")
        torch = None
    else:
        try:
            if not torch.cuda.is_available():
                missing.append("CUDA device is not available")
        except Exception as e:
            missing.append(f"torch.cuda check failed: {e}")

    for mod in ("diffusers", "transformers", "numpy", "imageio", "PIL"):
        try:
            __import__(mod)
        except Exception as e:
            missing.append(f"import {mod} failed: {e}")

    # Verify the specific pipeline entry point the task depends on, applying
    # the huggingface_hub compatibility shims first.
    try:
        _load_text_to_video_pipeline_cls()
    except Exception as e:
        missing.append(
            f"import TextToVideoSDPipeline failed: {type(e).__name__}: {e}"
        )

    if missing:
        print("doctor: MISSING requirements:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 78

    print("doctor: OK - inputs and dependencies available.")
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
def _verify_video(path, expected_frames):
    import imageio

    info = {"path": str(path), "decodable": False}
    try:
        reader = imageio.get_reader(str(path))
        decoded = []
        for fr in reader:
            decoded.append(fr)
        reader.close()
        info["num_decoded_frames"] = len(decoded)
        info["decode_shape"] = list(decoded[0].shape) if decoded else None
        info["decodable"] = len(decoded) == expected_frames
        if decoded:
            import numpy as np
            a = np.stack([np.asarray(f)[..., :3] for f in decoded]).astype(
                np.float32
            )
            info["decoded_mean"] = float(a.mean())
            info["decoded_std"] = float(a.std())
    except Exception as e:
        info["decode_error"] = str(e)
    return info


def _frame_stats(frame_np):
    import numpy as np

    a = np.asarray(frame_np, dtype=np.float32)
    if a.ndim == 3 and a.shape[-1] == 4:
        a = a[..., :3]
    return {
        "mean": float(a.mean()),
        "std": float(a.std()),
        "min": float(a.min()),
        "max": float(a.max()),
        "finite": bool(np.isfinite(a).all()),
    }


def cmd_run(args):
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for GPUv1-C04 but is not available; refusing to run."
        )

    import numpy as np
    import imageio  # noqa: F401

    TextToVideoSDPipeline = _load_text_to_video_pipeline_cls()
    export_to_video = _load_export_to_video()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    req_path = input_dir / "requests.jsonl"
    if not req_path.is_file():
        raise FileNotFoundError(f"Missing required input: {req_path}")
    reqs = _load_requests(req_path)

    model_path = _model_path()
    if not Path(model_path).is_dir():
        raise FileNotFoundError(f"Model not found at {model_path}")
    if not (Path(model_path) / "model_index.json").is_file():
        raise FileNotFoundError(
            f"Model directory {model_path} has no model_index.json"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    videos_dir = output_dir / "videos"
    frames_root = output_dir / "frames"
    videos_dir.mkdir(exist_ok=True)
    frames_root.mkdir(exist_ok=True)

    device = "cuda"
    print(
        f"[run] loading TextToVideoSDPipeline from {model_path} "
        f"(fp16, {device})",
        file=sys.stderr,
    )
    torch.cuda.synchronize()
    t_load0 = time.time()
    pipe = TextToVideoSDPipeline.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        local_files_only=True,
    )
    pipe = pipe.to(device)
    try:
        pipe.set_progress_bar_config(disable=True)
    except Exception:
        pass
    try:
        pipe.vae.enable_slicing()
    except Exception:
        pass
    torch.cuda.synchronize()
    t_load1 = time.time()
    load_seconds = t_load1 - t_load0

    base_seed = None if args.seed is None else int(args.seed)

    index_path = output_dir / "index.jsonl"
    index_entries = []
    total_gen_sync = 0.0
    t_run0 = time.time()

    with open(index_path, "w", encoding="utf-8") as idx_f:
        for i, req in enumerate(reqs):
            scene_id_raw = _id_of(req, i)
            scene_id = _sanitize(scene_id_raw)
            prompt = _prompt_of(req)
            seed = _request_seed(req, i, base_seed)

            generator = torch.Generator(device=device).manual_seed(seed)

            print(
                f"[run] scene={scene_id!r} seed={seed} "
                f"prompt={prompt[:70]!r}",
                file=sys.stderr,
            )
            torch.cuda.synchronize()
            t0 = time.time()
            with torch.inference_mode():
                result = pipe(
                    prompt=prompt,
                    num_frames=NUM_FRAMES,
                    height=HEIGHT,
                    width=WIDTH,
                    num_inference_steps=NUM_INFERENCE_STEPS,
                    guidance_scale=GUIDANCE_SCALE,
                    generator=generator,
                )
            torch.cuda.synchronize()
            t1 = time.time()
            gen_seconds = t1 - t0
            total_gen_sync += gen_seconds

            raw_frames = _extract_frames(result)
            if len(raw_frames) != NUM_FRAMES:
                raise RuntimeError(
                    f"expected {NUM_FRAMES} frames for {scene_id}, "
                    f"got {len(raw_frames)}"
                )

            # Convert float [0,1] frames to uint8 PIL images WITHOUT
            # mis-scaling (see _to_uint8_image). Validate finiteness first.
            frames = [_to_uint8_image(f) for f in raw_frames]

            scene_frames_dir = frames_root / scene_id
            scene_frames_dir.mkdir(parents=True, exist_ok=True)
            for fi, img in enumerate(frames):
                img.save(scene_frames_dir / f"frame_{fi:04d}.png")

            video_path = videos_dir / f"{scene_id}.mp4"
            export_to_video(frames, str(video_path), fps=FPS)

            decode_info = _verify_video(video_path, expected_frames=NUM_FRAMES)

            # Non-zero content check on real decoded frames (not on the source
            # float array) so that an empty/black output fails loudly.
            per_frame_stds = []
            all_finite = True
            for img in frames:
                st = _frame_stats(np.asarray(img))
                per_frame_stds.append(st["std"])
                all_finite = all_finite and st["finite"]
            min_std = min(per_frame_stds) if per_frame_stds else 0.0
            content_ok = bool(all_finite and min_std > 1.0)
            if not content_ok:
                raise RuntimeError(
                    f"generated video for {scene_id!r} appears blank/black "
                    f"(min per-frame std={min_std:.4f}); refusing to write "
                    f"a fake output."
                )

            entry = {
                "id": scene_id,
                "id_raw": scene_id_raw,
                "prompt": prompt,
                "seed": seed,
                "video": str(
                    (videos_dir / f"{scene_id}.mp4").relative_to(output_dir)
                ),
                "frames_dir": str(scene_frames_dir.relative_to(output_dir)),
                "num_frames": len(frames),
                "height": HEIGHT,
                "width": WIDTH,
                "fps": FPS,
                "num_inference_steps": NUM_INFERENCE_STEPS,
                "guidance_scale": GUIDANCE_SCALE,
                "generation_seconds_sync": gen_seconds,
                "frame_stats": {
                    "min_std": float(min_std),
                    "per_frame_std": [float(s) for s in per_frame_stds],
                    "all_finite": bool(all_finite),
                },
                "content_nonzero": True,
                "decode_check": decode_info,
            }
            idx_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            idx_f.flush()
            index_entries.append(entry)

    torch.cuda.synchronize()
    t_run1 = time.time()

    run_record = {
        "task_id": "GPUv1-C04",
        "variant": "debug",
        "model_repo": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_path": model_path,
        "pipeline": "TextToVideoSDPipeline",
        "precision": "fp16",
        "device": device,
        "gpu_name": torch.cuda.get_device_name(0),
        "protocol": {
            "height": HEIGHT,
            "width": WIDTH,
            "num_frames": NUM_FRAMES,
            "num_inference_steps": NUM_INFERENCE_STEPS,
            "guidance_scale": GUIDANCE_SCALE,
            "fps": FPS,
        },
        "seed_base": base_seed,
        "default_request_seed": DEFAULT_REQUEST_SEED,
        "input_file": str(req_path),
        "num_requests": len(reqs),
        "index_file": str(index_path.relative_to(output_dir)),
        "videos_dir": str(videos_dir.relative_to(output_dir)),
        "frames_dir": str(frames_root.relative_to(output_dir)),
        "frame_conversion": (
            "float32 [0,1] -> clip -> *255 -> rint -> uint8 (no double scale)"
        ),
        "timings": {
            "pipeline_load_seconds_sync": load_seconds,
            "total_generation_seconds_sync": total_gen_sync,
            "total_run_seconds": t_run1 - t_run0,
            "per_scene_seconds_sync": [
                e["generation_seconds_sync"] for e in index_entries
            ],
        },
        "outputs": index_entries,
    }
    with open(output_dir / "run.json", "w", encoding="utf-8") as f:
        json.dump(run_record, f, ensure_ascii=False, indent=2)

    print(f"[run] done: {len(reqs)} videos -> {output_dir}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "GPUv1-C04 debug variant - generate a playable video asset library "
            "with TextToVideoSDPipeline (damo-vilab/text-to-video-ms-1.7b), "
            "CUDA fp16, 256x256, 16 frames, 12 steps, guidance 7.5, 8 fps."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    pd = sub.add_parser(
        "doctor", help="check inputs/deps without running the model"
    )
    pd.add_argument("--input", required=True, help="input directory")

    pr = sub.add_parser("run", help="generate the video asset library")
    pr.add_argument("--input", required=True, help="input directory")
    pr.add_argument("--output", required=True, help="output directory")
    pr.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "base seed override; scene i uses seed + i. If omitted, each "
            "request's own 'seed' field is honored (fallback "
            f"{DEFAULT_REQUEST_SEED})."
        ),
    )
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
