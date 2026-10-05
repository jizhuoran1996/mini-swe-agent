#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPUv1-C08 (debug variant): text-to-audio environmental sound library.

AudioLDMPipeline (cvssp/audioldm-s-full-v2), CUDA fp16, audio_length_in_s=4,
12 inference steps, guidance_scale=2.5, 16 kHz WAV output.

Entry points
------------
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output [--seed N]

Notes on robustness
-------------------
* Some diffusers builds ship the (deprecated) AudioLDM pipeline together with a
  huggingface_hub version that no longer exports every helper that module imports
  (e.g. ``get_cached_repo_tree``).  Loading a *local* model directory never needs
  those helpers, so the loader below installs a clearly-labelled offline stub for
  missing ``huggingface_hub`` symbols and retries the import.  Every stub that was
  actually installed is reported in the log and in run.json.
* ``AudioLDMPipeline.__call__`` returns an ``AudioPipelineOutput`` dataclass
  (it has a ``.audios`` attribute), a tuple, or a raw array depending on the
  diffusers version.  The output extractor below normalises all of these.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib
import json
import os
import re
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

TASK_ID = "GPUv1-C08"
VARIANT = "debug"
MODEL_REPO = "cvssp/audioldm-s-full-v2"
MODEL_REVISION = "feeb3d14203495a4b6ac0893cbdedb2159b4819c"
DEFAULT_MODEL_PATH = Path("/models/cvssp--audioldm-s-full-v2")
AUDIO_LENGTH_S = 4.0
NUM_STEPS = 12
GUIDANCE = 2.5
SAMPLE_RATE = 16000
MIN_PEAK = 1e-4
EXIT_MISSING = 78

ID_KEYS = ("id", "request_id", "recording_id", "sample_id", "name")
PROMPT_KEYS = ("prompt", "caption", "text", "description", "sound_description", "event")
MODEL_COMPONENTS = ("unet", "vae", "text_encoder")

# module paths that have hosted AudioLDMPipeline across diffusers versions
PIPELINE_CANDIDATES = (
    ("diffusers.pipelines.audioldm.pipeline_audioldm", "AudioLDMPipeline"),
    ("diffusers.pipelines.audioldm", "AudioLDMPipeline"),
    ("diffusers.pipelines.deprecated.audioldm.pipeline_audioldm", "AudioLDMPipeline"),
    ("diffusers.pipelines.deprecated.audioldm", "AudioLDMPipeline"),
    ("diffusers.pipelines", "AudioLDMPipeline"),
    ("diffusers", "AudioLDMPipeline"),
)

# --------------------------------------------------------------------------- #
# huggingface_hub / diffusers import compatibility
# --------------------------------------------------------------------------- #
HF_SHIMS_INSTALLED: list = []
_MISSING_SYMBOL_RE = re.compile(r"cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]")
_KNOWN_ABSENT_HUB_SYMBOLS = (
    "get_cached_repo_tree",
    "get_cached_repo_tree_from_hf_cache",
    "CachedRepoTreeNotFoundError",
)
_KNOWN_ABSENT_HUB_MODULES = (
    "huggingface_hub",
    "huggingface_hub.utils",
    "huggingface_hub.errors",
)


def _exception_chain(exc):
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        yield cur
        cur = cur.__cause__ or cur.__context__


def _missing_hub_symbol(exc):
    """Return (symbol, module) for a missing huggingface_hub import, else None."""
    for err in _exception_chain(exc):
        for match in _MISSING_SYMBOL_RE.finditer(str(err)):
            name, module = match.group(1), match.group(2)
            if module == "huggingface_hub" or module.startswith("huggingface_hub."):
                return name, module
    return None


def _hub_stub(name, module):
    """Install an offline stub for a missing huggingface_hub symbol."""
    try:
        mod = importlib.import_module(module)
    except Exception:  # noqa: BLE001 - nothing to patch if the module itself is gone
        return False
    if hasattr(mod, name):
        return False

    if name.endswith("Error") or name.endswith("Exception"):
        def _stub(*args, **kwargs):  # pragma: no cover - only reached if unexpectedly called
            raise RuntimeError(
                f"{module}.{name} is not provided by the huggingface_hub version installed in "
                "this offline container; local-directory model loading does not require it."
            )
        _stub.__name__ = name
        _stub.__qualname__ = name
        try:
            _stub = type(name, (RuntimeError,), {"__doc__": _stub.__doc__})
        except Exception:  # noqa: BLE001
            pass
    else:
        def _stub(*args, **kwargs):  # pragma: no cover - only reached if unexpectedly called
            raise RuntimeError(
                f"{module}.{name} is not provided by the huggingface_hub version installed in "
                "this offline container; local-directory model loading does not require it."
            )
        _stub.__name__ = name
        _stub.__qualname__ = name

    setattr(mod, name, _stub)
    tag = f"{module}.{name}"
    if tag not in HF_SHIMS_INSTALLED:
        HF_SHIMS_INSTALLED.append(tag)
        print(f"[compat] stubbed missing offline symbol {tag}")
    return True


def _preinstall_known_hub_stubs():
    """Proactively patch hub helpers that recent diffusers expects but old hubs lack."""
    try:
        import huggingface_hub  # noqa: F401
    except Exception:  # noqa: BLE001
        return
    for name in _KNOWN_ABSENT_HUB_SYMBOLS:
        for module in _KNOWN_ABSENT_HUB_MODULES:
            try:
                _hub_stub(name, module)
            except Exception:  # noqa: BLE001
                pass


def import_with_hub_shims(module_path, attr=None, rounds=30):
    """Import ``attr`` from ``module_path``, retrying after patching hub symbols."""
    last_exc = None
    for _ in range(rounds):
        try:
            module = importlib.import_module(module_path)
            obj = getattr(module, attr) if attr else module
        except Exception as exc:  # noqa: BLE001 - inspect, then re-raise if unfixable
            last_exc = exc
            fix = _missing_hub_symbol(exc)
            if fix is not None and _hub_stub(fix[0], fix[1]):
                continue
            raise
        if attr and obj is None:
            raise ImportError(f"{module_path} does not expose {attr}")
        return obj
    raise ImportError(f"{module_path}: {last_exc}")


def _discover_audioldm_modules():
    """Filesystem scan for audioldm pipeline modules (cheap, no heavy imports)."""
    import diffusers

    root = Path(diffusers.__file__).resolve().parent
    found = []
    pipelines_dir = root / "pipelines"
    if not pipelines_dir.is_dir():
        return found
    for path in sorted(pipelines_dir.rglob("*.py")):
        name = path.name.lower()
        if "audioldm" not in name or "audioldm2" in name:
            continue
        parts = list(path.relative_to(root).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            found.append("diffusers." + ".".join(parts))
    return found


def load_audioldm_pipeline_class():
    """Return (AudioLDMPipeline, module_path) using local sources only."""
    _preinstall_known_hub_stubs()
    candidates = list(PIPELINE_CANDIDATES)
    try:
        for modname in _discover_audioldm_modules():
            entry = (modname, "AudioLDMPipeline")
            if entry not in candidates:
                candidates.append(entry)
    except Exception:  # noqa: BLE001 - discovery is best effort
        pass

    errors = []
    seen_classes = set()
    for module_path, attr in candidates:
        try:
            cls = import_with_hub_shims(module_path, attr)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{module_path}.{attr}: {type(exc).__name__}: {exc}")
            continue
        if isinstance(cls, type):
            if id(cls) in seen_classes:
                continue
            seen_classes.add(id(cls))
            return cls, module_path
        errors.append(f"{module_path}.{attr} is not a class")
    raise ImportError(
        "could not import AudioLDMPipeline from the installed diffusers. Attempts:\n  "
        + "\n  ".join(errors)
    )


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def first_present(obj: dict, keys):
    for key in keys:
        value = obj.get(key)
        if value is not None and value != "":
            return value
    return None


def safe_id(rid: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(rid))
    return cleaned[:120] or "item"


def load_requests(path: Path):
    """Read requests.jsonl (or a JSON array). Returns list of dicts."""
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    raw = []
    if stripped.startswith("["):
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON array: {exc}") from exc
    else:
        for lineno, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} invalid JSON: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path}: no requests found")

    requests, seen = [], set()
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: entry {idx} is not a JSON object")
        prompt = first_present(entry, PROMPT_KEYS)
        if prompt is None:
            raise ValueError(f"{path}: entry {idx} has no prompt/caption/text field")
        rid = first_present(entry, ID_KEYS)
        rid = str(rid) if rid is not None else f"req_{idx:04d}"
        if rid in seen:
            raise ValueError(f"{path}: duplicate request id {rid!r}")
        seen.add(rid)
        length = entry.get("audio_length_in_s")
        try:
            length = float(length) if length is not None else None
        except (TypeError, ValueError):
            length = None
        if length is not None and length <= 0:
            length = None
        seed = entry.get("seed")
        try:
            seed = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed = None
        requests.append({"id": rid, "prompt": str(prompt), "audio_length_in_s": length,
                         "seed": seed, "raw": entry})
    return requests


# --------------------------------------------------------------------------- #
# AudioLDMPipeline output normalisation
# --------------------------------------------------------------------------- #
def extract_waveform(pipeline_output):
    """Return a 2D/1D numpy float array from any AudioLDMPipeline return shape.

    Handles: AudioPipelineOutput(.audios), dict-like outputs, tuples/lists,
    torch tensors, numpy arrays.  The caller flattens and casts to float32.
    """
    import numpy as np

    out = pipeline_output
    # AudioPipelineOutput dataclass from diffusers
    audios = getattr(out, "audios", None)
    if audios is None and isinstance(out, dict):
        audios = out.get("audios")
    if audios is not None:
        out = audios
    # tuples/lists: first element is the audio batch in every diffusers pipeline
    if isinstance(out, (tuple, list)):
        if len(out) == 0:
            raise RuntimeError("pipeline returned an empty tuple/list")
        out = out[0]
        audios = getattr(out, "audios", None)
        if audios is not None:
            out = audios
        if isinstance(out, (tuple, list)):
            if len(out) == 0:
                raise RuntimeError("pipeline returned an empty audio container")
            out = out[0]
    # torch tensor -> numpy
    to_numpy = getattr(out, "detach", None)
    if callable(to_numpy):
        try:
            out = out.detach().cpu().numpy()
        except Exception:  # noqa: BLE001
            pass
    arr = np.asarray(out, dtype=np.float32)
    if arr.size == 0:
        raise RuntimeError("pipeline returned an empty waveform")
    return arr


def write_wav(path: Path, samples, sample_rate: int) -> None:
    import numpy as np

    data = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (data * 32767.0).round().astype("<i2")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with wave.open(str(tmp), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(int(sample_rate))
        fh.writeframes(pcm.tobytes())
    tmp.replace(path)


def verify_wav(path: Path):
    with wave.open(str(path), "rb") as fh:
        frames, rate = fh.getnframes(), fh.getframerate()
        channels, width = fh.getnchannels(), fh.getsampwidth()
    if frames <= 0 or rate <= 0 or channels <= 0 or width <= 0:
        raise RuntimeError(f"{path} is not a decodable non-empty WAV")
    return {"num_frames": frames, "sample_rate": rate, "channels": channels, "sample_width": width}


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def cmd_doctor(args) -> int:
    lines, problems = [], []

    def check(name: str, ok: bool, detail: str = ""):
        lines.append(("[OK]   " if ok else "[MISS] ") + name + (f" :: {detail}" if detail else ""))
        if not ok:
            problems.append(name)

    def warn(name: str, detail: str = ""):
        lines.append("[WARN] " + name + (f" :: {detail}" if detail else ""))

    input_dir = Path(args.input)
    requests_path = input_dir / "requests.jsonl"
    manifest_path = input_dir / "manifest.json"

    check("input directory", input_dir.is_dir(), str(input_dir))
    check("input/requests.jsonl present", requests_path.is_file(), str(requests_path))
    check("input/manifest.json present", manifest_path.is_file(), str(manifest_path))

    manifest = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            warn("manifest.json parse", str(exc))

    if requests_path.is_file():
        try:
            reqs = load_requests(requests_path)
            check("requests.jsonl parses", True, f"{len(reqs)} request(s)")
        except Exception as exc:  # noqa: BLE001
            check("requests.jsonl parses", False, str(exc))
        if manifest:
            expected = (manifest.get("files") or {}).get("requests.jsonl")
            actual = sha256_file(requests_path)
            if expected and expected != actual:
                warn("requests.jsonl sha256 differs from manifest", f"actual={actual}")
            elif expected:
                lines.append("[OK]   requests.jsonl sha256 matches manifest")
            check("manifest task_id", manifest.get("task_id") == TASK_ID,
                  str(manifest.get("task_id")))

    model_path = Path(args.model_path)
    check("model container dir", model_path.is_dir(), str(model_path))
    check("model_index.json", (model_path / "model_index.json").is_file())
    for comp in MODEL_COMPONENTS:
        check(f"model component '{comp}'", (model_path / comp).is_dir())

    for mod in ("torch", "numpy", "diffusers", "transformers"):
        try:
            imported = importlib.import_module(mod)
            lines.append(f"[OK]   python package '{mod}' importable "
                         f"({getattr(imported, '__version__', 'unknown')})")
        except Exception as exc:  # noqa: BLE001
            check(f"python package '{mod}'", False, str(exc))

    try:
        cls, module_path = load_audioldm_pipeline_class()
        check("AudioLDMPipeline importable", True,
              f"{module_path} (hub compat shims: {', '.join(HF_SHIMS_INSTALLED) or 'none'})")
    except Exception as exc:  # noqa: BLE001
        check("AudioLDMPipeline importable", False, str(exc).splitlines()[0])

    try:
        import torch

        check("torch CUDA available", torch.cuda.is_available(),
              torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no visible device")
        if torch.cuda.is_available():
            cap = torch.cuda.get_device_capability(0)
            lines.append(f"[OK]   device capability sm_{cap[0]}{cap[1]}, torch {torch.__version__}")
    except Exception:  # noqa: BLE001 - already reported by package check
        pass

    out_parent = os.path.dirname(os.path.abspath(args.output)) or "."
    check("output location writable", os.access(out_parent, os.W_OK), out_parent)

    print("\n".join(lines))
    if problems:
        print(f"\nMISSING/INVALID ({len(problems)}): " + "; ".join(problems))
        return EXIT_MISSING
    print("\nAll required inputs, model files and dependencies are available.")
    return 0


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def cmd_run(args) -> int:
    input_dir = Path(args.input)
    requests_path = input_dir / "requests.jsonl"
    if not requests_path.is_file():
        print(f"[error] required input file missing: {requests_path}", file=sys.stderr)
        return EXIT_MISSING
    try:
        requests = load_requests(requests_path)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    try:
        import numpy as np
        import torch
    except Exception as exc:  # noqa: BLE001
        print(f"[error] missing python dependency: {exc}", file=sys.stderr)
        return EXIT_MISSING

    if not torch.cuda.is_available():
        print("[error] CUDA is required for this task; no CUDA device is available.", file=sys.stderr)
        return EXIT_MISSING

    try:
        pipeline_cls, pipeline_module = load_audioldm_pipeline_class()
    except Exception as exc:  # noqa: BLE001
        print(f"[error] AudioLDMPipeline unavailable: {exc}", file=sys.stderr)
        return EXIT_MISSING
    print(f"[run] AudioLDMPipeline imported from {pipeline_module}")
    if HF_SHIMS_INSTALLED:
        print(f"[run] offline huggingface_hub compat shims: {', '.join(HF_SHIMS_INSTALLED)}")

    model_path = Path(args.model_path)
    if not (model_path / "model_index.json").is_file():
        print(f"[error] AudioLDM model not found at {model_path} (model_index.json missing)",
              file=sys.stderr)
        return EXIT_MISSING

    out_dir = Path(args.output)
    sounds_dir = out_dir / "sounds"
    audition_dir = out_dir / "audition"
    sounds_dir.mkdir(parents=True, exist_ok=True)
    audition_dir.mkdir(parents=True, exist_ok=True)

    pre_existing = [r["id"] for r in requests if (sounds_dir / f"{safe_id(r['id'])}.wav").exists()]

    wall_start = time.perf_counter()
    print(f"[run] loading {MODEL_REPO} from {model_path} (fp16, cuda)")
    load_t0 = time.perf_counter()
    try:
        pipe = pipeline_cls.from_pretrained(
            str(model_path), torch_dtype=torch.float16, local_files_only=True)
    except TypeError as exc:
        # newer diffusers renamed torch_dtype -> dtype
        if "torch_dtype" not in str(exc):
            raise
        print(f"[run] falling back to dtype= (torch_dtype rejected): {exc}")
        pipe = pipeline_cls.from_pretrained(
            str(model_path), dtype=torch.float16, local_files_only=True)
    pipe = pipe.to("cuda")
    pipe.set_progress_bar_config(disable=not args.progress)
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - load_t0

    sample_rate = None
    for attr in ("vocoder", "vae"):
        cfg = getattr(getattr(pipe, attr, None), "config", None)
        rate = getattr(cfg, "sampling_rate", None)
        if rate:
            sample_rate = int(rate)
            break
    sample_rate = sample_rate or SAMPLE_RATE

    torch.cuda.reset_peak_memory_stats()
    items, gpu_seconds_total = [], 0.0
    for idx, req in enumerate(requests):
        length = args.audio_length_in_s or req["audio_length_in_s"] or AUDIO_LENGTH_S
        seed = req["seed"] if req["seed"] is not None else (int(args.seed) + idx)
        generator = torch.Generator(device="cuda").manual_seed(int(seed))

        print(f"[run] {req['id']}: {length:.2f}s, steps={args.steps}, guidance={args.guidance}, seed={seed}")
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        audio = pipe(
            req["prompt"],
            audio_length_in_s=float(length),
            num_inference_steps=int(args.steps),
            guidance_scale=float(args.guidance),
            num_waveforms_per_prompt=1,
            generator=generator,
            output_type="np",
        )
        torch.cuda.synchronize()
        gpu_seconds = time.perf_counter() - t0

        waveform = extract_waveform(audio)
        wav = waveform.reshape(-1)
        if wav.size == 0:
            raise RuntimeError(f"request {req['id']}: pipeline returned an empty waveform")
        if not np.all(np.isfinite(wav)):
            raise RuntimeError(f"request {req['id']}: pipeline returned non-finite samples")
        peak = float(np.max(np.abs(wav)))
        if peak < MIN_PEAK:
            raise RuntimeError(f"request {req['id']}: pipeline returned silent audio (peak={peak:g})")

        wav_path = sounds_dir / f"{safe_id(req['id'])}.wav"
        write_wav(wav_path, wav, sample_rate)
        info = verify_wav(wav_path)
        if info["sample_rate"] != sample_rate:
            raise RuntimeError(f"request {req['id']}: unexpected sample rate in written WAV")

        gpu_seconds_total += gpu_seconds
        items.append({
            "id": req["id"],
            "prompt": req["prompt"],
            "audio_path": f"sounds/{wav_path.name}",
            "sample_rate": sample_rate,
            "num_samples": int(wav.size),
            "duration_s": round(wav.size / sample_rate, 6),
            "requested_audio_length_in_s": float(length),
            "seed": int(seed),
            "num_inference_steps": int(args.steps),
            "guidance_scale": float(args.guidance),
            "sha256": sha256_file(wav_path),
            "gpu_sync_seconds": round(gpu_seconds, 6),
            "peak_abs_amplitude": round(peak, 8),
        })
        print(f"[run]   -> {wav_path} ({items[-1]['duration_s']:.3f}s, {gpu_seconds:.2f}s GPU)")

    peak_mem_bytes = int(torch.cuda.max_memory_allocated())
    wall_seconds = time.perf_counter() - wall_start

    index_blob = "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items)
    (out_dir / "index.jsonl").write_text(index_blob, encoding="utf-8")
    (out_dir / "sound-library.jsonl").write_text(index_blob, encoding="utf-8")

    manifest_path = input_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None
    declared = (manifest or {}).get("files", {}).get("requests.jsonl")
    requests_sha = sha256_file(requests_path)

    rng_state = {
        "seeds": {it["id"]: it["seed"] for it in items},
        "torch_cpu_rng_state": torch.get_rng_state(),
        "torch_cuda_rng_state_all": torch.cuda.get_rng_state_all(),
    }
    try:
        torch.save(rng_state, out_dir / "rng_state.pt")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] could not persist rng_state.pt: {exc}", file=sys.stderr)

    config = {
        "task_id": TASK_ID,
        "variant": VARIANT,
        "model_repo": MODEL_REPO,
        "model_revision": MODEL_REVISION,
        "model_path": str(model_path),
        "pipeline_class": "AudioLDMPipeline",
        "pipeline_import_module": pipeline_module,
        "huggingface_hub_compat_shims": list(HF_SHIMS_INSTALLED),
        "torch_dtype": "float16",
        "device": "cuda",
        "audio_length_in_s": float(args.audio_length_in_s or AUDIO_LENGTH_S),
        "num_inference_steps": int(args.steps),
        "guidance_scale": float(args.guidance),
        "output_sample_rate": sample_rate,
        "channels": 1,
        "num_waveforms_per_prompt": 1,
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    run_record = {
        "task_id": TASK_ID,
        "variant": VARIANT,
        "scale": "debug_only",
        "formal_large_tested": False,
        "command": ["python", "solution/main.py"] + sys.argv[1:],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "requests_path": str(requests_path),
            "requests_sha256": requests_sha,
            "requests_manifest_sha256": declared,
            "requests_hash_matches_manifest": (declared == requests_sha) if declared else None,
            "manifest_path": str(manifest_path) if manifest_path.is_file() else None,
            "num_requests": len(requests),
        },
        "model": {
            "repo": MODEL_REPO,
            "revision": MODEL_REVISION,
            "container_path": str(model_path),
            "model_index_sha256": sha256_file(model_path / "model_index.json"),
            "pipeline_class": "AudioLDMPipeline",
            "pipeline_import_module": pipeline_module,
            "huggingface_hub_compat_shims": list(HF_SHIMS_INSTALLED),
            "torch_dtype": "float16",
            "device": "cuda",
        },
        "params": config,
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "device_name": torch.cuda.get_device_name(0),
            "device_capability": list(torch.cuda.get_device_capability(0)),
            "numpy": np.__version__,
            "diffusers": getattr(importlib.import_module("diffusers"), "__version__", None),
            "transformers": getattr(importlib.import_module("transformers"), "__version__", None),
            "huggingface_hub": getattr(importlib.import_module("huggingface_hub"), "__version__", None),
        },
        "items": items,
        "totals": {
            "num_items": len(items),
            "model_load_seconds": round(load_seconds, 6),
            "total_gpu_sync_seconds": round(gpu_seconds_total, 6),
            "wall_seconds": round(wall_seconds, 6),
            "peak_gpu_memory_bytes": peak_mem_bytes,
            "peak_gpu_memory_gib": round(peak_mem_bytes / (1024 ** 3), 4),
            "total_audio_seconds": round(sum(it["duration_s"] for it in items), 6),
        },
        "overwrote_pre_existing_files": pre_existing,
        "outputs": ["index.jsonl", "sound-library.jsonl", "config.json", "run.json",
                    "audition/index.html", "rng_state.pt", "sounds/<id>.wav"],
    }
    (out_dir / "run.json").write_text(json.dumps(run_record, indent=2, ensure_ascii=False),
                                       encoding="utf-8")

    rows = "\n".join(
        f'      <li><b>{html.escape(it["id"])}</b> — {html.escape(it["prompt"])} '
        f'({it["duration_s"]:.2f}s)<br>'
        f'<audio controls preload="none" src="../{it["audio_path"]}"></audio></li>'
        for it in items)
    (audition_dir / "index.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{TASK_ID} audition</title></head>\n<body>\n"
        f"  <h1>{TASK_ID} generated sound effects</h1>\n  <ul>\n{rows}\n  </ul>\n</body></html>\n",
        encoding="utf-8")

    print(json.dumps(run_record["totals"], indent=2))
    print(f"[run] done: {len(items)} item(s) -> {out_dir}")
    return 0


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(f"{TASK_ID} {VARIANT}: AudioLDM text-to-audio sound effects "
                     "(CUDA fp16, 16 kHz WAV)."))
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="generate the sound library")
    run_p.add_argument("--input", default="input", help="input directory (requests.jsonl)")
    run_p.add_argument("--output", default="output", help="output directory")
    run_p.add_argument("--seed", type=int, default=0,
                       help="base seed; request seed or seed+index is used")
    run_p.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    run_p.add_argument("--steps", type=int, default=NUM_STEPS)
    run_p.add_argument("--guidance", type=float, default=GUIDANCE)
    run_p.add_argument("--audio-length-in-s", type=float, default=None,
                       help="force a global audio length (default: request value or 4.0)")
    run_p.add_argument("--progress", action="store_true", help="show pipeline progress bars")
    run_p.set_defaults(func=cmd_run)

    doc_p = sub.add_parser("doctor", help="check inputs, model files and dependencies")
    doc_p.add_argument("--input", default="input")
    doc_p.add_argument("--output", default="output")
    doc_p.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    doc_p.set_defaults(func=cmd_doctor)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
