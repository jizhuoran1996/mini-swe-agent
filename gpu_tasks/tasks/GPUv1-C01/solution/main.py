#!/usr/bin/env python3
"""GPUv1-C01 debug variant: batch text-to-image with segmind/tiny-sd (CUDA fp16).

Commands
--------
  python solution/main.py --help
  python solution/main.py doctor   --input input
  python solution/main.py run      --input input --output output
  python solution/main.py generate --prompt TEXT --seed N --output PNG

Requires CUDA.  The upstream model is a trained distilled Stable Diffusion
checkpoint (segmind/tiny-sd) loaded from the read-only container path.
"""
import argparse
import json
import os
import sys
import time

MODEL_REPO = "segmind/tiny-sd"
MODEL_REVISION = "cad0bd7495fa6c4bcca01b19a723dc91627fe84f"
MODEL_PATH = "/models/segmind--tiny-sd"

WIDTH = 256
HEIGHT = 256
STEPS = 12
GUIDANCE = 7.5
DTYPE = "float16"


# ---------------------------------------------------------------------------
# huggingface_hub compatibility shim
# ---------------------------------------------------------------------------
# The frozen container ships a huggingface_hub that predates symbols the
# installed diffusers imports at module load time:
#   * ``huggingface_hub.get_cached_repo_tree``
#   * ``huggingface_hub.errors.CachedRepoTreeNotFoundError``
# Either missing symbol aborts the whole diffusers import graph, even though we
# always load the checkpoint from a local directory (``local_files_only=True``)
# and never actually reach these helpers.  The shim is inert at runtime; it
# only repairs the import graph so the real pipeline can be constructed.

def _install_huggingface_hub_shim():
    try:
        import huggingface_hub
    except Exception:
        return

    # --- missing error class ---------------------------------------------
    try:
        import huggingface_hub.errors as hf_errors
    except Exception:
        hf_errors = None

    def _make_error_class():
        base = Exception
        if hf_errors is not None:
            for name in ("EntryNotFoundError", "HfHubHTTPError", "HFValidationError"):
                cand = getattr(hf_errors, name, None)
                if isinstance(cand, type) and issubclass(cand, Exception):
                    base = cand
                    break

        class CachedRepoTreeNotFoundError(base):
            pass

        return CachedRepoTreeNotFoundError

    existing_err = None
    if hf_errors is not None:
        existing_err = getattr(hf_errors, "CachedRepoTreeNotFoundError", None)
    if existing_err is None:
        existing_err = getattr(huggingface_hub, "CachedRepoTreeNotFoundError", None)

    if existing_err is None:
        existing_err = _make_error_class()

    # Install into every plausible home so any ``from ... import ...`` works.
    targets = []
    if hf_errors is not None:
        targets.append(hf_errors)
    targets.append(huggingface_hub)
    for sub in ("huggingface_hub.utils", "huggingface_hub.hf_api",
                "huggingface_hub._snapshot_download"):
        try:
            targets.append(__import__(sub, fromlist=["*"]))
        except Exception:
            pass
    for mod in targets:
        if not hasattr(mod, "CachedRepoTreeNotFoundError"):
            try:
                setattr(mod, "CachedRepoTreeNotFoundError", existing_err)
            except Exception:
                pass

    # --- missing helper --------------------------------------------------
    if not hasattr(huggingface_hub, "get_cached_repo_tree"):
        def get_cached_repo_tree(repo_id, *args, **kwargs):
            from huggingface_hub import HfApi
            api = HfApi()
            kwargs.setdefault("repo_type", "model")
            return list(api.list_repo_tree(repo_id, *args, **kwargs))

        for mod in targets:
            if not hasattr(mod, "get_cached_repo_tree"):
                try:
                    setattr(mod, "get_cached_repo_tree", get_cached_repo_tree)
                except Exception:
                    pass


# Run the shim as early as possible, before any diffusers import can happen.
_install_huggingface_hub_shim()


def _fail(msg, code=1):
    print("error: " + str(msg), file=sys.stderr)
    return code


def load_pipeline():
    """Load tiny-sd on CUDA in fp16.  Raises on any prerequisite miss."""
    if not os.path.isdir(MODEL_PATH):
        raise RuntimeError("model directory not found: " + MODEL_PATH)
    try:
        import torch
    except Exception as exc:
        raise RuntimeError("torch not importable: %s" % exc)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required but torch.cuda.is_available() is False")

    _install_huggingface_hub_shim()
    try:
        from diffusers import StableDiffusionPipeline
    except Exception as exc:
        raise RuntimeError("diffusers not importable: %s" % exc)

    kwargs = dict(torch_dtype=torch.float16)
    try:
        pipe = StableDiffusionPipeline.from_pretrained(
            MODEL_PATH,
            safety_checker=None,
            requires_safety_checker=False,
            local_files_only=True,
            **kwargs,
        )
    except Exception:
        # some tiny checkpoints ship without the safety checker config
        pipe = StableDiffusionPipeline.from_pretrained(
            MODEL_PATH, local_files_only=True, **kwargs
        )
    pipe = pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    return pipe


def generate_one(pipe, prompt, seed):
    """Deterministic single-image generation with a fixed CUDA seed."""
    import torch
    gen = torch.Generator(device="cuda").manual_seed(int(seed))
    out = pipe(
        prompt,
        height=HEIGHT,
        width=WIDTH,
        num_inference_steps=STEPS,
        guidance_scale=GUIDANCE,
        generator=gen,
    )
    torch.cuda.synchronize()
    return out.images[0]


def _get(rec, *names, default=None):
    for n in names:
        if n in rec and rec[n] is not None:
            return rec[n]
    return default


def read_requests(path):
    reqs = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            reqs.append(json.loads(line))
    return reqs


def do_doctor(input_dir):
    missing = []
    checks = {}

    reqs = os.path.join(input_dir, "requests.jsonl") if input_dir else None
    if reqs and os.path.isfile(reqs):
        checks["requests.jsonl"] = "ok"
    else:
        checks["requests.jsonl"] = "missing"
        missing.append(reqs or "requests.jsonl")

    checks["model_path"] = "ok" if os.path.isdir(MODEL_PATH) else "missing"
    if not os.path.isdir(MODEL_PATH):
        missing.append(MODEL_PATH)

    _install_huggingface_hub_shim()

    try:
        import torch  # noqa: F401
        checks["torch"] = getattr(torch, "__version__", "unknown")
        if torch.cuda.is_available():
            checks["cuda"] = "available"
            try:
                checks["gpu"] = torch.cuda.get_device_name(0)
            except Exception:
                pass
        else:
            checks["cuda"] = "unavailable"
            missing.append("CUDA")
    except Exception as exc:
        checks["torch"] = "missing"
        missing.append("torch: %s" % exc)

    for pkg in ("huggingface_hub", "diffusers", "transformers", "numpy"):
        try:
            mod = __import__(pkg)
            checks[pkg] = getattr(mod, "__version__", "unknown")
        except Exception as exc:
            checks[pkg] = "missing"
            missing.append("%s: %s" % (pkg, exc))

    try:
        from PIL import Image  # noqa: F401
        checks["pillow"] = "ok"
    except Exception as exc:
        checks["pillow"] = "missing"
        missing.append("PIL: %s" % exc)

    print(json.dumps({"checks": checks, "missing": missing}, indent=2, ensure_ascii=False))
    return 78 if missing else 0


def do_run(input_dir, output_dir):
    reqs_path = os.path.join(input_dir, "requests.jsonl")
    if not os.path.isfile(reqs_path):
        return _fail("missing input file: " + reqs_path, 78)
    try:
        reqs = read_requests(reqs_path)
    except Exception as exc:
        return _fail("cannot parse requests.jsonl: %s" % exc, 78)
    if not reqs:
        return _fail("requests.jsonl contains no requests", 78)

    try:
        pipe = load_pipeline()
    except RuntimeError as exc:
        return _fail(exc, 1)

    import torch

    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    t0 = time.time()
    records = []
    gen_times = []
    try:
        for rec in reqs:
            rid = _get(rec, "id", "sample_id", "uid")
            if rid is None:
                return _fail("request without id: %r" % rec, 78)
            rid = str(rid)
            prompt = _get(rec, "prompt", "caption", "text")
            if prompt is None:
                return _fail("request %s without prompt" % rid, 78)
            seed = int(_get(rec, "seed", "random_seed", default=0))

            t_a = time.time()
            img = generate_one(pipe, prompt, seed)
            t_b = time.time()
            gen_times.append(t_b - t_a)

            out_path = os.path.join(images_dir, rid + ".png")
            img.convert("RGB").save(out_path)
            records.append(
                {
                    "id": rid,
                    "prompt": prompt,
                    "seed": seed,
                    "image": os.path.relpath(out_path, output_dir),
                    "parameters": {
                        "model": MODEL_REPO,
                        "revision": MODEL_REVISION,
                        "width": WIDTH,
                        "height": HEIGHT,
                        "steps": STEPS,
                        "guidance_scale": GUIDANCE,
                        "dtype": DTYPE,
                        "device": "cuda",
                    },
                }
            )
    except Exception as exc:
        return _fail("generation failed: %s" % exc, 1)

    with open(os.path.join(output_dir, "index.jsonl"), "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total_s = time.time() - t0
    run = {
        "task_id": "GPUv1-C01",
        "scale": "debug_only",
        "model_repo": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_path": MODEL_PATH,
        "device": "cuda",
        "dtype": DTYPE,
        "gpu_name": torch.cuda.get_device_name(0),
        "num_images": len(records),
        "config": {
            "width": WIDTH,
            "height": HEIGHT,
            "steps": STEPS,
            "guidance_scale": GUIDANCE,
        },
        "timings": {
            "generate_s": gen_times,
            "generate_total_s": sum(gen_times),
            "wall_total_s": total_s,
        },
    }
    with open(os.path.join(output_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=2, ensure_ascii=False)
    print(json.dumps({"images": len(records), "total_s": total_s}, ensure_ascii=False))
    return 0


def do_generate(prompt, seed, out_path):
    if not prompt:
        return _fail("--prompt is required", 78)
    try:
        pipe = load_pipeline()
    except RuntimeError as exc:
        return _fail(exc, 1)
    try:
        img = generate_one(pipe, prompt, int(seed))
    except Exception as exc:
        return _fail("generation failed: %s" % exc, 1)
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.convert("RGB").save(out_path)
    print(json.dumps({"image": out_path, "seed": int(seed)}, ensure_ascii=False))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-C01 debug generator (segmind/tiny-sd, CUDA fp16).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="process an input directory of requests")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)

    p_gen = sub.add_parser("generate", help="generate a single new image")
    p_gen.add_argument("--prompt", required=True)
    p_gen.add_argument("--seed", type=int, required=True)
    p_gen.add_argument("--output", required=True)

    p_doc = sub.add_parser("doctor", help="inspect inputs and dependencies only")
    p_doc.add_argument("--input", required=True)
    return parser


def main(argv=None):
    # Make sure the hub shim is in place before anything imports diffusers.
    _install_huggingface_hub_shim()
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return do_doctor(args.input)
    if args.command == "run":
        return do_run(args.input, args.output)
    if args.command == "generate":
        return do_generate(args.prompt, args.seed, args.output)
    return 2


if __name__ == "__main__":
    sys.exit(main())
