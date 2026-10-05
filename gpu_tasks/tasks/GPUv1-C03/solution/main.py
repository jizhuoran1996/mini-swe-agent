#!/usr/bin/env python3
"""
GPUv1-C03 (debug) - turn real photos into new assets under Canny edge constraints.

Pipeline:
  * read <input>/requests.jsonl (id -> source photo)
  * OpenCV Canny(low=100, high=200) at 512x512 -> edge conditioning image
  * StableDiffusionControlNetPipeline + sd-controlnet-canny, CUDA fp16
  * 12 steps, guidance 7.5, controlnet_conditioning_scale 1.0
  * write  <out>/control/<id>.png  and  <out>/images/<id>.png
  * write  <out>/index.jsonl  and  <out>/run.json

CLI:
    python solution/main.py --help
    python solution/main.py doctor --input input
    python solution/main.py run    --input input --output output

The `mask` field of a request is intentionally ignored for this task.
"""

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np

TASK_ID = "GPUv1-C03"
SCALE = "debug_only"
CONTROLNET_PATH = "/models/lllyasviel--sd-controlnet-canny"
SD_PATH = "/models/stable-diffusion-v1-5--stable-diffusion-v1-5"

DIM = 512
STEPS = 12
GUIDANCE = 7.5
COND_SCALE = 1.0
CANNY_LOW = 100
CANNY_HIGH = 200

EXIT_MISSING = 78
EXIT_NO_CUDA = 2
EXIT_ERROR = 1


# --------------------------------------------------------------------------- #
# Compatibility shim
#
# Older `huggingface_hub` shipped alongside a newer `diffusers` in this
# container is missing a few names that the diffusers import path expects.
# We install inert, well-scoped placeholders BEFORE importing diffusers so
# the import statements resolve.  All model loading in this task uses local
# directories (/models/...), so none of these placeholders are ever used at
# runtime; they only need to exist so that `from ... import ...` succeeds.
# --------------------------------------------------------------------------- #
def _make_cached_repo_tree_not_found_error():
    # Prefer to reuse the real class if a newer huggingface_hub defines it
    # elsewhere (e.g. top-level), so downstream `except` clauses still work.
    try:
        import huggingface_hub as _hf_top
        existing = getattr(_hf_top, "CachedRepoTreeNotFoundError", None)
        if isinstance(existing, type):
            return existing
    except Exception:
        pass
    # Otherwise create a class that subclasses common base error types so
    # generic `except Exception`, `except OSError`, and the typical
    # huggingface_hub base (if any) all still catch it.
    bases = []
    try:
        import huggingface_hub.errors as _hfe
        base = getattr(_hfe, "HfHubHTTPError", None) or getattr(_hfe, "HFHubError", None)
        if isinstance(base, type):
            bases.append(base)
    except Exception:
        pass
    bases.append(OSError)
    # Deduplicate while preserving resolution order.
    uniq = []
    for b in bases:
        if b not in uniq:
            uniq.append(b)
    return type("CachedRepoTreeNotFoundError", tuple(uniq), {})


def _ensure_hf_compat():
    try:
        import huggingface_hub as hf
    except Exception:
        return

    # ---- huggingface_hub.errors additions -------------------------------- #
    try:
        import huggingface_hub.errors as hferr
    except Exception:
        hferr = None

    err_cls = _make_cached_repo_tree_not_found_error()

    for target in (hf, hferr):
        if target is None:
            continue
        if not hasattr(target, "CachedRepoTreeNotFoundError"):
            try:
                setattr(target, "CachedRepoTreeNotFoundError", err_cls)
            except Exception:
                pass

    # ---- huggingface_hub top-level additions the diffusers import wants -- #
    if not hasattr(hf, "get_cached_repo_tree"):
        def get_cached_repo_tree(repo_id, *args, **kwargs):
            """Minimal local-cache listing. Never touches the network."""
            revision = kwargs.get("revision")
            cache_dir = kwargs.get("cache_dir")
            try:
                from huggingface_hub import scan_cache_dir
                info = scan_cache_dir(cache_dir)
            except Exception:
                return []
            entries = []
            try:
                for repo in info.repos:
                    if getattr(repo, "repo_id", None) != repo_id:
                        continue
                    for rev in repo.revisions:
                        if revision and revision not in (
                            getattr(rev, "commit_hash", None),
                            getattr(rev, "ref", None),
                        ):
                            continue
                        for f in rev.files:
                            p = getattr(f, "file_path", None)
                            if p is not None:
                                entries.append(p)
            except Exception:
                return []
            return entries
        hf.get_cached_repo_tree = get_cached_repo_tree

    if not hasattr(hf, "DDUFEntry"):
        class DDUFEntry(object):
            pass
        hf.DDUFEntry = DDUFEntry
    if not hasattr(hf, "DDUFExportError"):
        class DDUFExportError(RuntimeError):
            pass
        hf.DDUFExportError = DDUFExportError
    if not hasattr(hf, "export_entries_as_dduf"):
        def export_entries_as_dduf(*a, **k):
            raise NotImplementedError("DDUF export not available in this environment")
        hf.export_entries_as_dduf = export_entries_as_dduf
    if not hasattr(hf, "read_dduf_file"):
        def read_dduf_file(*a, **k):
            raise NotImplementedError("DDUF reading not available in this environment")
        hf.read_dduf_file = read_dduf_file

    # ---- propagate to any pre-imported huggingface_hub.* submodules ------ #
    for name, mod in list(sys.modules.items()):
        if mod is None or not name.startswith("huggingface_hub"):
            continue
        for attr in ("get_cached_repo_tree", "DDUFEntry", "DDUFExportError",
                     "export_entries_as_dduf", "read_dduf_file",
                     "CachedRepoTreeNotFoundError"):
            if hasattr(hf, attr) and not hasattr(mod, attr):
                try:
                    setattr(mod, attr, getattr(hf, attr))
                except Exception:
                    pass


_ensure_hf_compat()


# --------------------------------------------------------------------------- #
# small IO helpers
# --------------------------------------------------------------------------- #
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path):
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                items.append(json.loads(s))
    return items


def resolve_id(req, idx):
    for key in ("id", "image_id", "name", "key"):
        v = req.get(key)
        if v is not None and str(v) != "":
            return str(v)
    return str(idx)


def resolve_image(req, input_dir):
    """Return the on-disk path of the photo referenced by a request."""
    for key in ("image", "image_path", "path", "image_file", "img"):
        v = req.get(key)
        if isinstance(v, str) and v.strip():
            cand = v.strip()
            if os.path.isabs(cand):
                return cand
            for base in (input_dir, os.path.join(input_dir, "images")):
                p = os.path.join(base, cand)
                if os.path.exists(p):
                    return p
            p = os.path.join(input_dir, os.path.basename(cand))
            if os.path.exists(p):
                return p
            return os.path.join(input_dir, cand)
    rid = req.get("id", req.get("image_id", req.get("name")))
    if rid is not None and str(rid) != "":
        for cand in (os.path.join(input_dir, "images", "%s.png" % rid),
                     os.path.join(input_dir, "%s.png" % rid)):
            if os.path.exists(cand):
                return cand
        return os.path.join(input_dir, "images", "%s.png" % rid)
    return None


def resolve_prompt(req):
    prompt = req.get("prompt")
    base = prompt.strip() if isinstance(prompt, str) and prompt.strip() else ""
    if not base:
        for key in ("caption", "description", "text", "style_prompt"):
            v = req.get(key)
            if isinstance(v, str) and v.strip():
                base = v.strip()
                break
    style = req.get("style_brief") or req.get("style")
    if isinstance(style, str) and style.strip() and style.strip() not in base:
        base = (base + ", " + style.strip()).strip(", ")
    return base or "a detailed illustration, high quality, layout preserved"


def deterministic_seed(rid):
    digest = hashlib.sha256((TASK_ID + ":" + rid).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)  # stable 32-bit seed, replayable


# --------------------------------------------------------------------------- #
# Canny edges (cv2 preferred, pure-numpy fallback with identical thresholds)
# --------------------------------------------------------------------------- #
def _convolve(img, kernel):
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2
    padded = np.pad(img, ((ph, ph), (pw, pw)), mode="reflect")
    out = np.zeros(img.shape, dtype=np.float64)
    for i in range(kh):
        for j in range(kw):
            out += kernel[i, j] * padded[i:i + img.shape[0], j:j + img.shape[1]]
    return out


def _gaussian(size=5, sigma=1.4):
    ax = np.arange(size) - (size // 2)
    xx, yy = np.meshgrid(ax, ax)
    k = np.exp(-(xx * xx + yy * yy) / (2.0 * sigma * sigma))
    return k / k.sum()


def _dilate(mask):
    p = np.pad(mask, 1)
    return (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] |
            p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:])


def _canny_numpy(gray, low, high):
    blurred = _convolve(gray, _gaussian())
    gx = _convolve(blurred, np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64))
    gy = _convolve(blurred, np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float64))
    mag = np.hypot(gx, gy)
    ang = np.degrees(np.arctan2(gy, gx)) % 180.0
    q = np.floor((ang + 22.5) / 45.0).astype(np.int32) % 4
    p = np.pad(mag, 1)
    n1 = np.zeros_like(mag)
    n2 = np.zeros_like(mag)
    m = q == 0
    n1[m] = p[1:-1, 0:-2][m]; n2[m] = p[1:-1, 2:][m]
    m = q == 1
    n1[m] = p[0:-2, 2:][m]; n2[m] = p[2:, 0:-2][m]
    m = q == 2
    n1[m] = p[0:-2, 1:-1][m]; n2[m] = p[2:, 1:-1][m]
    m = q == 3
    n1[m] = p[0:-2, 0:-2][m]; n2[m] = p[2:, 2:][m]
    nms = np.where((mag >= n1) & (mag >= n2), mag, 0.0)
    strong = nms > high
    weak = (nms > low) & ~strong
    edges = strong.copy()
    for _ in range(64):
        grown = edges | (_dilate(edges) & weak)
        if np.array_equal(grown, edges):
            break
        edges = grown
    return (edges.astype(np.uint8)) * 255


def canny_edges(pil_img, low=CANNY_LOW, high=CANNY_HIGH):
    """3-channel uint8 Canny image at the requested size."""
    gray = np.asarray(pil_img.convert("L"), dtype=np.uint8)
    try:
        import cv2
        edges = cv2.Canny(gray, low, high)
    except Exception:
        edges = _canny_numpy(gray.astype(np.float64), low, high)
    return np.stack([edges, edges, edges], axis=-1).astype(np.uint8)


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def _collect_missing(input_dir):
    missing = []
    req_path = os.path.join(input_dir, "requests.jsonl")
    for p in (req_path, os.path.join(input_dir, "manifest.json"),
              CONTROLNET_PATH, SD_PATH):
        if not os.path.exists(p):
            missing.append(p)
    for mod in ("torch", "diffusers", "transformers", "numpy", "PIL"):
        try:
            __import__(mod)
        except Exception:
            missing.append("python-module:%s" % mod)
    if os.path.exists(req_path):
        try:
            reqs = read_jsonl(req_path)
            for i, req in enumerate(reqs):
                rid = resolve_id(req, i)
                p = resolve_image(req, input_dir)
                if not p or not os.path.exists(p):
                    missing.append("image for id=%s -> %s" % (rid, p))
        except Exception as exc:
            missing.append("requests.jsonl unreadable: %s" % exc)
    return missing


def cmd_doctor(args):
    input_dir = args.input
    missing = _collect_missing(input_dir)
    cuda = False
    gpu_name = None
    try:
        import torch
        cuda = bool(torch.cuda.is_available())
        if cuda:
            gpu_name = torch.cuda.get_device_name(0)
    except Exception:
        cuda = False
    report = {
        "task_id": TASK_ID,
        "scale": SCALE,
        "input": os.path.abspath(input_dir),
        "cuda_available": cuda,
        "gpu_name": gpu_name,
        "controlnet_path": CONTROLNET_PATH,
        "base_model_path": SD_PATH,
        "missing": missing,
        "ok": len(missing) == 0,
    }
    print(json.dumps(report, indent=2))
    return 0 if not missing else EXIT_MISSING


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def cmd_run(args):
    input_dir = args.input
    out_dir = args.output

    missing = _collect_missing(input_dir)
    if missing:
        print(json.dumps({"status": "missing", "missing": missing}, indent=2))
        return EXIT_MISSING

    import torch
    if not torch.cuda.is_available():
        print(json.dumps({"status": "error", "error": "CUDA is not available"}))
        return EXIT_NO_CUDA

    _ensure_hf_compat()  # re-assert after torch import, in case HF was (re)loaded

    from PIL import Image
    from diffusers import ControlNetModel, StableDiffusionControlNetPipeline

    started = time.time()
    os.makedirs(os.path.join(out_dir, "control"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "images"), exist_ok=True)

    controlnet = ControlNetModel.from_pretrained(
        CONTROLNET_PATH, torch_dtype=torch.float16
    )
    pipe = StableDiffusionControlNetPipeline.from_pretrained(
        SD_PATH,
        controlnet=controlnet,
        torch_dtype=torch.float16,
        safety_checker=None,
        requires_safety_checker=False,
    )
    pipe = pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass

    req_path = os.path.join(input_dir, "requests.jsonl")
    requests = read_jsonl(req_path)

    index_lines = []
    run_requests = []
    total_sync = 0.0

    for i, req in enumerate(requests):
        rid = resolve_id(req, i)
        img_path = resolve_image(req, input_dir)
        prompt = resolve_prompt(req)
        seed = deterministic_seed(rid)
        in_hash = sha256_file(img_path)

        photo = Image.open(img_path).convert("RGB").resize(
            (DIM, DIM), Image.LANCZOS
        )
        canny = canny_edges(photo, CANNY_LOW, CANNY_HIGH)
        control_img = Image.fromarray(canny)
        control_path = os.path.join(out_dir, "control", "%s.png" % rid)
        control_img.save(control_path)

        torch.manual_seed(seed)
        generator = torch.Generator(device="cpu").manual_seed(seed)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        result = pipe(
            prompt=prompt,
            image=control_img,
            num_inference_steps=STEPS,
            guidance_scale=GUIDANCE,
            controlnet_conditioning_scale=COND_SCALE,
            generator=generator,
            height=DIM,
            width=DIM,
        )
        torch.cuda.synchronize()
        dt = time.perf_counter() - t0
        total_sync += dt

        out_path = os.path.join(out_dir, "images", "%s.png" % rid)
        result.images[0].save(out_path)

        index_lines.append({
            "id": rid,
            "input": os.path.abspath(img_path),
            "input_sha256": in_hash,
            "control": os.path.relpath(control_path, out_dir),
            "output": os.path.relpath(out_path, out_dir),
            "prompt": prompt,
            "seed": seed,
            "steps": STEPS,
            "guidance_scale": GUIDANCE,
            "conditioning_scale": COND_SCALE,
            "width": DIM,
            "height": DIM,
        })
        run_requests.append({
            "id": rid,
            "input": os.path.abspath(img_path),
            "input_sha256": in_hash,
            "control": os.path.relpath(control_path, out_dir),
            "output": os.path.relpath(out_path, out_dir),
            "prompt": prompt,
            "seed": seed,
            "sync_seconds": round(dt, 4),
        })

    with open(os.path.join(out_dir, "index.jsonl"), "w", encoding="utf-8") as f:
        for entry in index_lines:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    try:
        import diffusers
        diffusers_version = diffusers.__version__
    except Exception:
        diffusers_version = None

    run_info = {
        "task_id": TASK_ID,
        "scale": SCALE,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "device": "cuda:0",
        "gpu_name": torch.cuda.get_device_name(0),
        "dtype": "float16",
        "torch_version": torch.__version__,
        "diffusers_version": diffusers_version,
        "model": {
            "controlnet": CONTROLNET_PATH,
            "base": SD_PATH,
        },
        "generation": {
            "width": DIM,
            "height": DIM,
            "steps": STEPS,
            "guidance_scale": GUIDANCE,
            "conditioning_scale": COND_SCALE,
            "canny_low": CANNY_LOW,
            "canny_high": CANNY_HIGH,
        },
        "num_requests": len(run_requests),
        "total_sync_seconds": round(total_sync, 4),
        "wall_seconds": round(time.time() - started, 4),
        "requests": run_requests,
    }
    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(run_info, f, indent=2, ensure_ascii=False)

    print(json.dumps({
        "status": "ok",
        "output": os.path.abspath(out_dir),
        "num_requests": len(run_requests),
        "total_sync_seconds": round(total_sync, 4),
    }, indent=2))
    return 0


# --------------------------------------------------------------------------- #
def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-C03 debug: Canny-ControlNet SD1.5 image transformation",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="run Canny-ControlNet generation over requests.jsonl")
    p_run.add_argument("--input", default="input")
    p_run.add_argument("--output", default="output")

    p_doc = sub.add_parser("doctor", help="inspect required inputs/dependencies without running models")
    p_doc.add_argument("--input", default="input")
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "run":
        return cmd_run(args)
    parser.print_help()
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
