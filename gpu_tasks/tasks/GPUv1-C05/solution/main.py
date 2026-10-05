#!/usr/bin/env python3
"""GPUv1-C05 (debug variant): animate genuine COCO reference images into short clips.

Unified entry point:

    python solution/main.py --help
    python solution/main.py doctor --input input
    python solution/main.py run --input input --output output [--seed N]

The real work (StableVideoDiffusionPipeline, CUDA fp16, 14 frames, 256x256,
12 steps, decode_chunk_size=2, motion_bucket_id=127, noise_aug_strength=0.02,
7 fps) only happens in `run`.  It requires a working CUDA device and the
pre-provisioned local model, and it writes clips, per-frame PNGs, contact
sheets, index.jsonl and run.json under --output.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

TASK_ID = "GPUv1-C05"
MODEL_REPO = "stabilityai/stable-video-diffusion-img2vid"
MODEL_REVISION = "9cf024d5bfa8f56622af86c884f26a52f6676f2e"
DEFAULT_MODEL_DIR = "/models/stabilityai--stable-video-diffusion-img2vid"
REQUIRED_INPUT_FILES = ("reference.jpg", "requests.jsonl", "manifest.json")
MODEL_SUBDIRS = ("unet", "vae", "image_encoder", "scheduler", "feature_extractor")

P = {
    "num_frames": 14,
    "height": 256,
    "width": 256,
    "num_inference_steps": 12,
    "decode_chunk_size": 2,
    "motion_bucket_id": 127,
    "noise_aug_strength": 0.02,
    "fps": 7,
}


# ------------------------------------------------------------------ hf shims
# The container pins a `huggingface_hub` that predates symbols the pinned
# `diffusers` imports unconditionally:
#
#   * ``huggingface_hub.get_cached_repo_tree``
#   * ``huggingface_hub.errors.CachedRepoTreeNotFoundError``
#
# Without them, importing ``diffusers.pipelines.stable_video_diffusion``
# fails at import time (which is exactly the ``model_load_failed`` error we
# saw).  We cannot upgrade or install packages here, so we install local-only
# stand-ins *before* diffusers is ever imported.  The stand-ins only read the
# local HF cache directory; they never touch the network.

_HF_SHIM_DONE = False
_HF_SHIM_INSTALLED: list = []


def _install_huggingface_hub_shims() -> list:
    global _HF_SHIM_DONE, _HF_SHIM_INSTALLED
    if _HF_SHIM_DONE:
        return list(_HF_SHIM_INSTALLED)
    installed: list = []

    try:
        import huggingface_hub as hub
    except Exception as exc:  # noqa: BLE001
        _HF_SHIM_DONE = True
        _HF_SHIM_INSTALLED = installed
        return [f"huggingface_hub unavailable: {exc}"]

    # 1) ``huggingface_hub.errors.CachedRepoTreeNotFoundError``
    # diffusers does ``from huggingface_hub.errors import ...`` and crashes
    # if the symbol is absent.  Provide a FileNotFoundError subclass.
    try:
        from huggingface_hub import errors as hub_errors  # type: ignore
    except Exception:  # noqa: BLE001
        hub_errors = None

    cached_err_cls = getattr(hub_errors, "CachedRepoTreeNotFoundError", None) if hub_errors else None
    if cached_err_cls is None:
        class CachedRepoTreeNotFoundError(FileNotFoundError):  # noqa: D401
            """Local stand-in for the missing hub exception class."""

        if hub_errors is not None and not hasattr(hub_errors, "CachedRepoTreeNotFoundError"):
            hub_errors.CachedRepoTreeNotFoundError = CachedRepoTreeNotFoundError
            installed.append("huggingface_hub.errors.CachedRepoTreeNotFoundError")
        if not hasattr(hub, "CachedRepoTreeNotFoundError"):
            hub.CachedRepoTreeNotFoundError = CachedRepoTreeNotFoundError
            if hub_errors is None:
                installed.append("huggingface_hub.CachedRepoTreeNotFoundError")

    # 2) ``huggingface_hub.get_cached_repo_tree``
    if not hasattr(hub, "get_cached_repo_tree"):
        class _RepoFile:
            __slots__ = ("path", "size", "blob_id", "lfs", "type")

            def __init__(self, path, size=None, blob_id=None, lfs=None):
                self.path = path
                self.size = size
                self.blob_id = blob_id
                self.lfs = lfs
                self.type = "file"

            def __repr__(self) -> str:
                return f"RepoFile(path={self.path!r})"

        def get_cached_repo_tree(repo_id=None, *_args, **_kwargs):
            """Return the locally cached file tree for `repo_id`.

            Only the local HF cache root is searched; if nothing is present an
            empty list is returned so callers can continue with
            ``local_files_only`` loading.
            """
            try:
                from huggingface_hub import constants as hub_constants
                cache_root = Path(getattr(hub_constants, "HF_HUB_CACHE", "") or
                                  (Path.home() / ".cache" / "huggingface" / "hub"))
                if not repo_id or not cache_root.is_dir():
                    return []
                slug = "models--" + str(repo_id).replace("/", "--")
                snapshots = cache_root / slug / "snapshots"
                if not snapshots.is_dir():
                    return []
                files = []
                for snap in sorted(p for p in snapshots.iterdir() if p.is_dir()):
                    for entry in sorted(snap.rglob("*")):
                        if entry.is_file():
                            try:
                                rel = str(entry.relative_to(snap))
                            except ValueError:
                                continue
                            files.append(_RepoFile(rel))
                return files
            except Exception:  # noqa: BLE001
                return []

        hub.get_cached_repo_tree = get_cached_repo_tree
        installed.append("huggingface_hub.get_cached_repo_tree")

    _HF_SHIM_DONE = True
    _HF_SHIM_INSTALLED = installed
    return list(installed)


def load_pipeline(model_dir: Path):
    import torch

    shims = _install_huggingface_hub_shims()
    if shims:
        print(f"[info] installed huggingface_hub shims: {', '.join(shims)}", file=sys.stderr)

    from diffusers import StableVideoDiffusionPipeline  # shims must be installed first

    kwargs = dict(torch_dtype=torch.float16, local_files_only=True, add_watermarker=False)
    try:
        pipe = StableVideoDiffusionPipeline.from_pretrained(str(model_dir), variant="fp16", **kwargs)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] fp16-variant load failed ({exc}); retrying without variant", file=sys.stderr)
        pipe = StableVideoDiffusionPipeline.from_pretrained(str(model_dir), **kwargs)
    pipe.to("cuda")
    try:
        pipe.set_progress_bar_config(disable=True)
    except Exception:  # noqa: BLE001
        pass
    return pipe


# ---------------------------------------------------------------- input layer

def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sanitize_id(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._-")
    return (clean or "request")[:100]


def dump(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def verify_hashes(input_dir: Path):
    manifest_path = input_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {}, {"files": {}, "problems": [f"cannot parse manifest.json: {exc}"]}
    files = manifest.get("files") or {}
    problems, report = [], {}
    if not files:
        problems.append("manifest.json contains no 'files' hash mapping")
    for name, expected in files.items():
        candidate = input_dir / name
        if not candidate.exists():
            problems.append(f"manifest lists missing input file: {candidate}")
            continue
        actual = sha256_file(candidate)
        report[name] = {
            "expected_sha256": expected,
            "actual_sha256": actual,
            "match": bool(actual == expected),
        }
        if actual != expected:
            problems.append(f"sha256 mismatch for {name}: expected {expected}, got {actual}")
    return manifest, {"files": report, "problems": problems}


def parse_requests(path: Path):
    text = path.read_text(encoding="utf-8")
    objects = []
    stripped = text.strip()
    if stripped.startswith("["):
        data = json.loads(stripped)
        objects = data if isinstance(data, list) else [data]
    else:
        for lineno, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"requests.jsonl line {lineno}: {exc}") from exc
            objects.extend(obj if isinstance(obj, list) else [obj])

    requests = []
    for idx, obj in enumerate(objects):
        if not isinstance(obj, dict):
            raise ValueError(f"request #{idx} is not a JSON object")
        rid = (obj.get("request_id") or obj.get("id") or obj.get("name")
               or obj.get("image_name") or f"req{idx:03d}")
        prompt = (obj.get("prompt") or obj.get("text") or obj.get("caption")
                  or obj.get("motion_prompt") or "")
        image = (obj.get("image") or obj.get("image_path") or obj.get("reference_image")
                 or obj.get("reference") or obj.get("image_name") or "reference.jpg")
        seed = obj.get("seed")
        requests.append({
            "index": idx,
            "request_id": sanitize_id(rid),
            "raw_request_id": str(rid),
            "prompt": str(prompt),
            "image": str(image),
            "seed": int(seed) if isinstance(seed, (int, float)) else None,
            "raw": obj,
        })
    if not requests:
        raise ValueError("requests.jsonl contains no usable requests")
    return requests


def image_candidates(input_dir: Path, raw: str):
    raw_path = Path(raw)
    candidates = []
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(input_dir / raw_path)
        candidates.append(input_dir / raw_path.name)
    base = input_dir / raw_path.name
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        candidates.append(base.with_suffix(ext))
        candidates.append(input_dir / (raw_path.name + ext))
    return candidates


def resolve_image(input_dir: Path, raw: str):
    for candidate in image_candidates(input_dir, raw):
        if candidate.is_file():
            try:
                candidate.resolve().relative_to(input_dir.resolve())
            except ValueError:
                continue
            return candidate, True
    return None, False


# ----------------------------------------------------------------- model layer

def model_problems(model_dir: Path):
    problems = []
    if not model_dir.is_dir():
        return [f"model container path not found: {model_dir}"]
    if not (model_dir / "model_index.json").is_file():
        problems.append(f"missing {model_dir / 'model_index.json'}")
    for sub in MODEL_SUBDIRS:
        subdir = model_dir / sub
        if not subdir.is_dir():
            problems.append(f"missing model subdirectory: {subdir}")
            continue
        if sub in ("unet", "vae", "image_encoder"):
            weights = list(subdir.glob("*.safetensors")) + list(subdir.glob("*.bin"))
            if not weights:
                problems.append(f"no weight file (*.safetensors/*.bin) under {subdir}")
    return problems


def model_warnings(model_dir: Path):
    warnings = []
    if model_dir.is_dir() and not (model_dir / "preprocessor_config.json").is_file():
        warnings.append(f"{model_dir / 'preprocessor_config.json'} not present")
    return warnings


# ------------------------------------------------------------ output writing

def write_video(frames_u8, path: Path, fps: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    errors = []

    try:
        import imageio.v2 as imageio
        try:
            imageio.mimwrite(str(path), list(frames_u8), fps=fps, codec="libx264", quality=8,
                             macro_block_size=None, output_params=["-pix_fmt", "yuv420p"],
                             ffmpeg_log_level="error")
        except TypeError:
            imageio.mimwrite(str(path), list(frames_u8), fps=fps, codec="libx264",
                             quality=8, macro_block_size=None)
        if path.exists() and path.stat().st_size > 0:
            return "imageio-ffmpeg"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"imageio: {exc}")

    if path.exists():
        path.unlink()
    try:
        import torch
        import torchvision  # noqa: F401
        from torchvision.io import write_video as tv_write_video
        tensor = torch.from_numpy(frames_u8.copy())
        tv_write_video(str(path), tensor, fps=fps)
        if path.exists() and path.stat().st_size > 0:
            return "torchvision"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"torchvision: {exc}")

    if path.exists():
        path.unlink()
    try:
        import cv2
        height, width = frames_u8.shape[1], frames_u8.shape[2]
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (width, height))
        if not writer.isOpened():
            raise RuntimeError("cv2.VideoWriter could not be opened")
        for frame in frames_u8:
            writer.write(frame[:, :, ::-1])
        writer.release()
        if path.exists() and path.stat().st_size > 0:
            return "opencv-mp4v"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"opencv: {exc}")

    raise RuntimeError("no usable MP4 writer backend: " + "; ".join(errors))


def verify_video(path: Path, expected_frames: int):
    try:
        import imageio.v2 as imageio
        reader = imageio.get_reader(str(path))
        count = None
        try:
            count = int(reader.count_frames())
        finally:
            reader.close()
        return {"decoder": "imageio", "decoded_frames": count, "ok": count == expected_frames}
    except Exception as exc:  # noqa: BLE001
        return {"decoder": None, "decoded_frames": None, "ok": None, "error": str(exc)}


def make_contact_sheet(frames_u8, path: Path, cols: int = 7):
    from PIL import Image
    count, height, width = frames_u8.shape[0], frames_u8.shape[1], frames_u8.shape[2]
    rows = (count + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * height), (0, 0, 0))
    for index in range(count):
        tile = Image.fromarray(frames_u8[index])
        sheet.paste(tile, ((index % cols) * width, (index // cols) * height))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def update_run_json(path: Path, entry: dict):
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    data["task_id"] = TASK_ID
    data["model"] = {"repo": MODEL_REPO, "revision": MODEL_REVISION,
                     "dtype": "float16", "runtime": "cuda"}
    data["protocol"] = dict(P)
    runs = data.setdefault("runs", [])
    runs.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ----------------------------------------------------------------- doctor cmd

def cmd_doctor(args) -> int:
    input_dir = Path(args.input)
    model_dir = Path(args.model)
    problems, warnings = [], []
    info = {}

    input_info = {"path": str(input_dir), "files": {}}
    if not input_dir.is_dir():
        problems.append(f"input directory not found: {input_dir}")
    else:
        for name in REQUIRED_INPUT_FILES:
            candidate = input_dir / name
            exists = candidate.is_file()
            input_info["files"][name] = {
                "path": str(candidate),
                "exists": exists,
                "bytes": candidate.stat().st_size if exists else None,
                "sha256": sha256_file(candidate) if exists else None,
            }
            if not exists:
                problems.append(f"required input file missing: {candidate}")
        if all((input_dir / n).is_file() for n in REQUIRED_INPUT_FILES):
            _, hash_report = verify_hashes(input_dir)
            input_info["sha256_manifest_check"] = hash_report["files"]
            problems.extend(hash_report["problems"])
            try:
                parsed = parse_requests(input_dir / "requests.jsonl")
                input_info["requests"] = [
                    {"request_id": r["request_id"], "image": r["image"], "seed": r["seed"]}
                    for r in parsed
                ]
            except Exception as exc:  # noqa: BLE001
                problems.append(f"cannot parse requests.jsonl: {exc}")
    info["input"] = input_info

    info["model"] = {"path": str(model_dir)}
    problems.extend(model_problems(model_dir))
    warnings.extend(model_warnings(model_dir))

    env = {"python": sys.version.split()[0], "packages": {}}
    for module in ("torch", "torchvision", "diffusers", "transformers", "numpy", "PIL",
                   "imageio", "imageio_ffmpeg", "cv2", "accelerate", "safetensors",
                   "huggingface_hub"):
        try:
            spec = importlib.util.find_spec(module)
        except Exception:  # noqa: BLE001
            spec = None
        env["packages"][module] = {"available": spec is not None,
                                   "origin": getattr(spec, "origin", None) if spec else None}
    info["environment"] = env

    # Report/execute the compatibility shims so doctor surfaces the same import
    # environment that `run` will use, without ever loading model weights.
    installed_shims = _install_huggingface_hub_shims()
    env["huggingface_hub_shims"] = installed_shims

    if not env["packages"]["torch"]["available"]:
        problems.append("PyTorch is not importable")
    else:
        try:
            import torch
            env["torch_version"] = torch.__version__
            env["cuda_available"] = bool(torch.cuda.is_available())
            if torch.cuda.is_available():
                env["cuda_device_count"] = torch.cuda.device_count()
                env["cuda_device_name"] = torch.cuda.get_device_name(0)
                env["cuda_capability"] = ".".join(str(v) for v in torch.cuda.get_device_capability(0))
            else:
                problems.append("CUDA is not available; the generation task requires a GPU")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"cannot inspect torch/CUDA: {exc}")

    if not env["packages"]["diffusers"]["available"]:
        problems.append("diffusers is not importable (StableVideoDiffusionPipeline unavailable)")
        env["stable_video_diffusion_pipeline"] = False
    else:
        try:
            import diffusers
            env["diffusers_version"] = getattr(diffusers, "__version__", None)
            from diffusers import StableVideoDiffusionPipeline  # noqa: F401
            env["stable_video_diffusion_pipeline"] = True
        except Exception as exc:  # noqa: BLE001
            env["stable_video_diffusion_pipeline"] = False
            problems.append(f"cannot import StableVideoDiffusionPipeline: {exc}")

    if not env["packages"]["transformers"]["available"]:
        problems.append("transformers is not importable")
    if not env["packages"]["PIL"]["available"]:
        problems.append("Pillow is not importable")

    video_backends = [
        name for name in ("imageio", "imageio_ffmpeg", "cv2", "torchvision")
        if env["packages"].get(name, {}).get("available")
    ]
    info["video_backends"] = video_backends
    if not video_backends:
        problems.append("no MP4 writer backend available (need imageio+imageio-ffmpeg, cv2 or torchvision)")
    elif "imageio_ffmpeg" not in video_backends and "cv2" not in video_backends:
        warnings.append("MP4 writing will fall back to a non-imageio backend")

    dump({
        "task_id": TASK_ID,
        "status": "ok" if not problems else "missing",
        "info": info,
        "problems": problems,
        "warnings": warnings,
    })
    return 0 if not problems else 78


# -------------------------------------------------------------------- run cmd

def cmd_run(args) -> int:
    started = time.time()
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    model_dir = Path(args.model)

    problems = []
    if not input_dir.is_dir():
        problems.append(f"input directory not found: {input_dir}")
    else:
        for name in REQUIRED_INPUT_FILES:
            if not (input_dir / name).is_file():
                problems.append(f"required input file missing: {input_dir / name}")
    if problems:
        dump({"task_id": TASK_ID, "status": "missing_input", "problems": problems})
        return 78

    _, hash_report = verify_hashes(input_dir)
    if hash_report["problems"]:
        dump({"task_id": TASK_ID, "status": "missing_input",
              "problems": hash_report["problems"], "hash_report": hash_report["files"]})
        return 78

    installed_shims = _install_huggingface_hub_shims()

    try:
        import numpy as np
        import torch
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        dump({"task_id": TASK_ID, "status": "missing_dependency", "problems": [f"import failed: {exc}"]})
        return 78

    if not torch.cuda.is_available():
        dump({"task_id": TASK_ID, "status": "missing_dependency",
              "problems": ["CUDA is not available; this task must run on a GPU"]})
        return 78

    model_probs = model_problems(model_dir)
    if model_probs:
        dump({"task_id": TASK_ID, "status": "missing_model", "problems": model_probs})
        return 78

    try:
        requests = parse_requests(input_dir / "requests.jsonl")
    except Exception as exc:  # noqa: BLE001
        dump({"task_id": TASK_ID, "status": "missing_input", "problems": [f"requests.jsonl: {exc}"]})
        return 78

    default_image = input_dir / "reference.jpg"
    if not default_image.is_file():
        dump({"task_id": TASK_ID, "status": "missing_input",
              "problems": [f"no reference.jpg to fall back on in {input_dir}"]})
        return 78

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "clips").mkdir(exist_ok=True)
    (output_dir / "frames").mkdir(exist_ok=True)
    (output_dir / "review-contact-sheets").mkdir(exist_ok=True)

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    base_seed = args.seed if args.seed is not None else 0

    gpu_name = torch.cuda.get_device_name(0)
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    load_t0 = time.perf_counter()
    try:
        pipe = load_pipeline(model_dir)
    except Exception as exc:  # noqa: BLE001
        dump({"task_id": TASK_ID, "status": "model_load_failed", "problems": [str(exc)]})
        return 78
    torch.cuda.synchronize()
    model_load_s = time.perf_counter() - load_t0

    index_path = output_dir / "index.jsonl"
    ref_map_path = output_dir / "reference-map.jsonl"
    request_records, failures = [], []
    inference_total_s = 0.0
    encode_total_s = 0.0
    video_backend = None

    for req in requests:
        rid = req["request_id"]
        seed = (req["seed"] if (args.seed is None and req["seed"] is not None)
                else int(base_seed) + int(req["index"]))
        seed = int(seed) % (2 ** 31 - 1)

        image_path, matched = resolve_image(input_dir, req["image"])
        fallback = False
        if image_path is None:
            image_path, fallback = default_image, True
            print(f"[warn] requested image {req['image']!r} not found; "
                  f"using declared input reference.jpg", file=sys.stderr)

        pil_image = Image.open(image_path).convert("RGB").resize(
            (P["width"], P["height"]), Image.LANCZOS)
        generator = torch.Generator(device="cuda").manual_seed(seed)

        call_kwargs = dict(
            image=pil_image,
            height=P["height"],
            width=P["width"],
            num_frames=P["num_frames"],
            num_inference_steps=P["num_inference_steps"],
            decode_chunk_size=P["decode_chunk_size"],
            motion_bucket_id=P["motion_bucket_id"],
            noise_aug_strength=P["noise_aug_strength"],
            fps=P["fps"],
            generator=generator,
            output_type="np",
        )

        torch.cuda.synchronize()
        inf_t0 = time.perf_counter()
        try:
            try:
                result = pipe(**call_kwargs)
            except TypeError as exc:
                print(f"[warn] pipeline call rejected fps: {exc}", file=sys.stderr)
                call_kwargs.pop("fps", None)
                result = pipe(**call_kwargs)
        except Exception as exc:  # noqa: BLE001
            failures.append({"request_id": rid, "error": f"inference failed: {exc}"})
            print(f"[error] {rid}: inference failed: {exc}", file=sys.stderr)
            continue
        torch.cuda.synchronize()
        inference_s = time.perf_counter() - inf_t0
        inference_total_s += inference_s

        frames = np.asarray(result.frames[0], dtype=np.float32)
        if frames.ndim != 4 or frames.shape[0] != P["num_frames"]:
            failures.append({"request_id": rid, "error": f"unexpected frame shape {frames.shape}"})
            continue
        if not np.isfinite(frames).all():
            failures.append({"request_id": rid, "error": "non-finite values in generated frames"})
            continue

        frames_u8 = np.clip(frames * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)

        frames_dir = output_dir / "frames" / rid
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        frames_dir.mkdir(parents=True, exist_ok=True)
        for i in range(frames_u8.shape[0]):
            Image.fromarray(frames_u8[i]).save(frames_dir / f"frame_{i:03d}.png")

        clip_path = output_dir / "clips" / f"{rid}.mp4"
        request_video_dir = output_dir / rid
        request_video_dir.mkdir(parents=True, exist_ok=True)
        request_video_path = request_video_dir / "video.mp4"

        torch.cuda.synchronize()
        enc_t0 = time.perf_counter()
        try:
            backend = write_video(frames_u8, clip_path, P["fps"])
            shutil.copyfile(clip_path, request_video_path)
        except Exception as exc:  # noqa: BLE001
            failures.append({"request_id": rid, "error": f"video encode failed: {exc}"})
            print(f"[error] {rid}: video encode failed: {exc}", file=sys.stderr)
            continue
        torch.cuda.synchronize()
        encode_s = time.perf_counter() - enc_t0
        encode_total_s += encode_s
        video_backend = backend

        sheet_path = output_dir / "review-contact-sheets" / f"{rid}.png"
        make_contact_sheet(frames_u8, sheet_path)

        diff = np.abs(frames_u8[0].astype(np.int16) - frames_u8[-1].astype(np.int16))
        record = {
            "run_id": run_id,
            "task_id": TASK_ID,
            "request_id": rid,
            "raw_request_id": req["raw_request_id"],
            "prompt": req["prompt"],
            "seed": seed,
            "image": str(image_path.relative_to(input_dir)),
            "image_sha256": sha256_file(image_path),
            "image_match": matched,
            "image_fallback": fallback,
            "clip": str(clip_path.relative_to(output_dir)),
            "video": str(request_video_path.relative_to(output_dir)),
            "frames_dir": str(frames_dir.relative_to(output_dir)),
            "contact_sheet": str(sheet_path.relative_to(output_dir)),
            "num_frames": int(frames_u8.shape[0]),
            "height": int(frames_u8.shape[1]),
            "width": int(frames_u8.shape[2]),
            "fps": P["fps"],
            "duration_s": P["num_frames"] / float(P["fps"]),
            "num_inference_steps": P["num_inference_steps"],
            "decode_chunk_size": P["decode_chunk_size"],
            "motion_bucket_id": P["motion_bucket_id"],
            "noise_aug_strength": P["noise_aug_strength"],
            "motion_delta": float(diff.mean()),
            "temporal_std": float(frames_u8.std(axis=0).mean()),
            "inference_s": inference_s,
            "video_encode_s": encode_s,
            "video_backend": backend,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        record["video_decode_check"] = verify_video(clip_path, P["num_frames"])
        request_records.append(record)

        with open(index_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        with open(ref_map_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "run_id": run_id,
                "request_id": rid,
                "reference_image": str(image_path.relative_to(input_dir)),
                "reference_sha256": record["image_sha256"],
                "fallback_to_default_reference": fallback,
            }, ensure_ascii=False) + "\n")
        print(f"[ok] {rid}: seed={seed} image={record['image']} "
              f"inference={inference_s:.2f}s encode={encode_s:.2f}s clip={record['clip']}")

    torch.cuda.synchronize()
    total_wall_s = time.time() - started
    peak_gib = torch.cuda.max_memory_allocated() / (1024 ** 3)

    run_entry = {
        "run_id": run_id,
        "task_id": TASK_ID,
        "status": "ok" if (request_records and not failures) else "failed",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "input_files": hash_report["files"],
        "seed_base_arg": args.seed,
        "model": {"repo": MODEL_REPO, "revision": MODEL_REVISION,
                  "container_path": str(model_dir), "dtype": "float16"},
        "protocol": dict(P),
        "gpu": {"name": gpu_name,
                "total_memory_gib": torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)},
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "diffusers": getattr(__import__("diffusers"), "__version__", None),
            "transformers": getattr(__import__("transformers"), "__version__", None),
            "huggingface_hub_shims": installed_shims,
        },
        "timings_gpu_synchronized_s": {
            "model_load": model_load_s,
            "inference_total": inference_total_s,
            "video_encode_total": encode_total_s,
        },
        "wall_clock_s": total_wall_s,
        "peak_device_memory_gib": peak_gib,
        "video_backend": video_backend,
        "requests": request_records,
        "failures": failures,
    }
    update_run_json(output_dir / "run.json", run_entry)
    dump({"task_id": TASK_ID, "status": run_entry["status"], "run_id": run_id,
          "requests_done": len(request_records), "failures": failures,
          "wall_clock_s": total_wall_s, "index": str(index_path), "run_json": str(output_dir / "run.json")})

    if failures or not request_records:
        return 1
    return 0


# ---------------------------------------------------------------------- entry

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=f"{TASK_ID} debug variant: stable-video-diffusion image animation on CUDA.",
    )
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor",
                            help="inspect inputs, model files and dependencies (no model execution)")
    doctor.add_argument("--input", default="input")
    doctor.add_argument("--model", default=DEFAULT_MODEL_DIR)

    run = sub.add_parser("run", help="generate the videos / frame PNGs on the local GPU")
    run.add_argument("--input", default="input")
    run.add_argument("--output", default="output")
    run.add_argument("--model", default=DEFAULT_MODEL_DIR)
    run.add_argument("--seed", type=int, default=None,
                     help=("base seed override; request i uses seed+i "
                           "(requests' own seeds are used when not given)"))

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
