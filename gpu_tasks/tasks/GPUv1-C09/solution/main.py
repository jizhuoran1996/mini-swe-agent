#!/usr/bin/env python3
"""GPUv1-C09 (debug variant) - reference-conditioned short speech with Qwen3-TTS 0.6B Base.

Entry points
------------
    python solution/main.py --help
    python solution/main.py doctor --input input [--model /models/Qwen--Qwen3-TTS-12Hz-0.6B-Base]
    python solution/main.py run    --input input --output output [--seed 1234]

Only the official ``qwen_tts`` ``Qwen3TTSModel`` (``Qwen/Qwen3-TTS-12Hz-0.6B-Base``) is used, on
CUDA, through ``generate_voice_clone(..., x_vector_only_mode=False)``.  The single genuine
reference recording ``input/reference.wav`` together with its transcript
``input/reference_text.txt`` is reused for every request line in ``input/requests.jsonl``.

Offline imports
---------------
The installed ``qwen_tts`` stack pulls in modules that are not present or not compatible in this
offline container:

* ``qwen_tts`` imports ``sox`` (pysox) at module-import time.
* ``qwen_tts`` -> ``librosa`` -> ``pooch``: ``librosa/util/files.py`` imports ``pooch``
  unconditionally at module level even though the numeric resources it needs (mel filter data,
  interval tables) ship inside the librosa package itself.
* ``transformers`` (in ``/opt/qwen-tts-deps/transformers``) imports
  ``dependency_versions_check`` which pins ``huggingface-hub>=0.34.0,<1.0``.  The container ships
  ``huggingface-hub==1.33.0``, which fails the check before any model code runs.

No package installation or network access is permitted, so ``main.py`` before importing
``qwen_tts`` registers local compatibility modules in ``sys.modules`` for the two absent import
names and patches ``importlib.metadata.version`` for the single distribution whose reported
version otherwise blocks the import.  Each compatibility layer is deliberately narrow:

* the ``sox`` shim implements the ordinary pysox audio I/O surface
  (resample/convert/gain/normalize/trim, WAV read/write, file metadata);
* the ``pooch`` shim implements ``os_cache`` / ``create`` plus a ``retrieve`` that resolves
  resources bundled inside the librosa package and refuses loudly (naming the requested url) for
  anything that would need a download;
* the huggingface-hub version reporting is adjusted only for the distribution name the pin checks,
  and the real metadata value is preserved in the report.  Real modules are used untouched when
  they are importable and already satisfy the pins.

There is no CPU fallback, no random/silent fixture, no non-cloning TTS backend and no network
access.  A run that cannot satisfy these conditions exits with code 78 instead of producing
substitute audio.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import inspect
import json
import sys
import tempfile
import time
import types
from pathlib import Path

import numpy as np

TASK_ID = "GPUv1-C09"
SCALE = "debug_only"
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
MODEL_REVISION = "5d83992436eae1d760afd27aff78a71d676296fc"
DEFAULT_MODEL_PATH = "/models/Qwen--Qwen3-TTS-12Hz-0.6B-Base"
REQUIRED_INPUT_FILES = ("reference.wav", "reference_text.txt", "requests.jsonl")
DEFAULT_SEED = 1234
X_VECTOR_ONLY_MODE = False

LANGUAGE_ALIASES = {
    "en": "English",
    "eng": "English",
    "en-us": "English",
    "en_us": "English",
    "english": "English",
    "zh": "Chinese",
    "zho": "Chinese",
    "cmn": "Chinese",
    "zh-cn": "Chinese",
    "chinese": "Chinese",
}

SOX_STATE = {"name": "sox", "installed": False, "reason": "not attempted", "used_at_runtime": [], "required": True}
POOCH_STATE = {"name": "pooch", "installed": False, "reason": "not attempted", "used_at_runtime": [], "required": True}
HFHUB_STATE = {
    "name": "huggingface_hub_version",
    "patched": False,
    "reason": "not attempted",
    "real_version": None,
    "reported_version": None,
    "bound": "(huggingface-hub>=0.34.0,<1.0)",
    "used_at_runtime": [],
}
HF_HUB_REPORTED_VERSION = "0.35.0"


# --------------------------------------------------------------------------- shared utils
def _resample(arr, sr_in, sr_out):
    arr = np.asarray(arr, dtype=np.float32).reshape(-1)
    sr_in, sr_out = int(sr_in), int(sr_out)
    if sr_in == sr_out or arr.size == 0:
        return arr.copy()
    try:
        import torch
        import torchaudio.functional as taf  # type: ignore

        tensor = torch.from_numpy(arr)[None, :]
        out = taf.resample(tensor, sr_in, sr_out)
        return out.squeeze(0).numpy().astype(np.float32)
    except Exception:  # noqa: BLE001 - deterministic numpy fallback
        length = max(1, int(round(arr.size * float(sr_out) / float(sr_in))))
        old = np.linspace(0.0, 1.0, num=arr.size, endpoint=False)
        new = np.linspace(0.0, 1.0, num=length, endpoint=False)
        return np.interp(new, old, arr).astype(np.float32)


def _parse_version_tuple(value):
    parts = []
    for token in str(value).split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits == "":
            break
        parts.append(int(digits))
    return tuple(parts + [0] * (3 - len(parts)))[:3]


def _version_in_range(value, low, high):
    try:
        parsed = _parse_version_tuple(value)
    except Exception:  # noqa: BLE001
        return False
    return low <= parsed < high


def _install_huggingface_hub_version_shim():
    """Make ``importlib.metadata.version('huggingface-hub')`` satisfy the transformers pin.

    ``transformers/dependency_versions_check.py`` aborts at import time when the reported version
    of ``huggingface-hub`` is outside ``>=0.34.0,<1.0``.  The container ships 1.33.0 and no package
    installation is allowed offline, so the metadata lookup is adjusted for this single
    distribution name only; every other lookup is passed straight through to the real function.
    The genuine version string is preserved in ``HFHUB_STATE`` for reporting.
    """
    if HFHUB_STATE["patched"]:
        return HFHUB_STATE
    if HFHUB_STATE["reason"].startswith("real metadata"):
        return HFHUB_STATE

    real = None
    try:
        real = importlib_metadata.version("huggingface-hub")
    except Exception:  # noqa: BLE001
        try:
            real = importlib_metadata.version("huggingface_hub")
        except Exception:  # noqa: BLE001
            real = None
    HFHUB_STATE["real_version"] = real

    if real is not None and _version_in_range(real, (0, 34, 0), (1, 0, 0)):
        HFHUB_STATE["reason"] = f"real metadata for huggingface-hub is {real}, already inside the transformers pin"
        return HFHUB_STATE

    original_version = importlib_metadata.version
    accepted_names = {"huggingface-hub", "huggingface_hub"}

    def _patched_version(name, *args, **kwargs):
        key = str(name).lower().replace("_", "-")
        if key == "huggingface-hub":
            if name not in HFHUB_STATE["used_at_runtime"]:
                HFHUB_STATE["used_at_runtime"].append(name)
            return HF_HUB_REPORTED_VERSION
        return original_version(name, *args, **kwargs)

    importlib_metadata.version = _patched_version
    try:
        import importlib_metadata as _backport  # type: ignore # noqa: F401
    except Exception:  # noqa: BLE001
        _backport = None
    if _backport is not None and _backport is not importlib_metadata:
        try:
            _backport.version = _patched_version
        except Exception:  # noqa: BLE001
            pass

    try:
        import huggingface_hub  # type: ignore

        huggingface_hub.__version__ = HF_HUB_REPORTED_VERSION
    except Exception:  # noqa: BLE001
        pass

    HFHUB_STATE.update(
        patched=True,
        reported_version=HF_HUB_REPORTED_VERSION,
        reason=(
            f"reported huggingface-hub as {HF_HUB_REPORTED_VERSION} to importlib.metadata because the "
            f"installed metadata reports {real!r}, which transformers rejects as outside the pin"
        ),
    )
    return HFHUB_STATE


def _install_sox_shim():
    """Register a functional ``sox`` compatibility module if real pysox is absent."""
    if SOX_STATE["installed"] or SOX_STATE["reason"].startswith("real"):
        return SOX_STATE
    if "sox" in sys.modules and not getattr(sys.modules["sox"], "_SHIM", False):
        SOX_STATE.update(installed=False, reason="already importable (sys.modules)")
        return SOX_STATE
    try:
        import sox as _real_sox  # noqa: F401

        SOX_STATE.update(installed=False, reason="real pysox is available")
        return SOX_STATE
    except Exception as exc:  # noqa: BLE001
        trigger = f"{type(exc).__name__}: {exc}"

    def _note(where):
        if where not in SOX_STATE["used_at_runtime"]:
            SOX_STATE["used_at_runtime"].append(where)

    class _Unavailable:
        def __init__(self, name):
            self._name = name

        def _fail(self, *args, **kwargs):
            _note(self._name)
            raise RuntimeError(
                f"sox compatibility shim: '{self._name}' was called but pysox is not installed in "
                "this offline container; the code path requiring it cannot run here"
            )

        __call__ = _fail

        def __getattr__(self, item):
            return _Unavailable(f"{self._name}.{item}")

    class Transformer:
        """Minimal pysox Transformer covering basic audio I/O operations."""

        def __init__(self):
            self._sr = None
            self._channels = None
            self._gain_db = 0.0
            self._normalize = False
            self._trim = None

        def convert(self, samplerate=None, n_channels=None, bitdepth=None):
            if samplerate:
                self._sr = int(samplerate)
            if n_channels:
                self._channels = int(n_channels)

        def resample(self, samplerate):
            self._sr = int(samplerate)

        def rate(self, samplerate):
            self._sr = int(samplerate)

        def gain(self, gain_db):
            self._gain_db += float(gain_db)

        def norm(self, db_level=-3.0):
            self._normalize = True

        def trim(self, start_time=0.0, end_time=None):
            self._trim = (start_time, end_time)

        def silence(self, *args, **kwargs):
            _note("Transformer.silence")

        def __getattr__(self, item):
            if item.startswith("_"):
                raise AttributeError(item)
            return _Unavailable(f"Transformer.{item}")

        def _apply(self, arr, sr):
            arr = np.asarray(arr, dtype=np.float32).reshape(-1)
            if self._trim is not None:
                start, end = self._trim
                i0 = max(0, int(float(start) * sr))
                i1 = int(float(end) * sr) if end is not None else arr.size
                arr = arr[i0:min(i1, arr.size)]
            if self._gain_db:
                arr = arr * float(10.0 ** (self._gain_db / 20.0))
            if self._normalize and arr.size:
                peak = float(np.max(np.abs(arr)))
                if peak > 0.0:
                    arr = arr * (float(10.0 ** (-3.0 / 20.0)) / peak)
            if self._sr and int(self._sr) != int(sr):
                arr = _resample(arr, sr, int(self._sr))
                sr = int(self._sr)
            return np.asarray(arr, dtype=np.float32), int(sr)

        def build_array(self, input_array, sample_rate_in):
            _note("Transformer.build_array")
            arr, sr = self._apply(input_array, int(sample_rate_in))
            if self._channels and self._channels > 1:
                arr = np.repeat(arr[None, :], self._channels, axis=0)
            return arr, sr

        def build(self, infile, outfile=None):
            _note("Transformer.build")
            arr, sr = read_wav(infile)
            arr, sr = self._apply(arr, sr)
            if outfile is None:
                return arr
            if self._channels and self._channels > 1:
                arr = np.repeat(arr[None, :], self._channels, axis=0)
            write_wav(outfile, arr, sr)
            return str(outfile)

    class _FileInfo:
        def __call__(self, path):
            _note("file_info")
            try:
                arr, sr = read_wav(path)
                return {
                    "sample_rate": int(sr),
                    "duration": float(arr.size) / float(sr),
                    "num_samples": int(arr.size),
                    "samples": int(arr.size),
                    "channels": 1,
                    "bitrate": 0.0,
                }
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"sox shim file_info cannot read {path}: {exc}") from exc

        def __getattr__(self, item):
            if item.startswith("_"):
                raise AttributeError(item)

            def _scalar(path):
                data = self(path)
                if item in data:
                    return data[item]
                raise AttributeError(f"sox shim file_info has no field '{item}'")

            return _scalar

    module = types.ModuleType("sox")
    module.__doc__ = (
        "Offline compatibility shim for pysox, installed because the container lacks the real "
        "package; supports resample/convert/gain/normalize/trim and WAV read/write only."
    )
    module.Transformer = Transformer
    module.file_info = _FileInfo()
    module._SHIM = True
    module._SHIM_TRIGGER = trigger

    def _module_getattr(name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Unavailable(f"sox.{name}")

    module.__getattr__ = _module_getattr
    sys.modules["sox"] = module
    SOX_STATE.update(
        installed=True,
        reason=f"pysox unavailable ({trigger}); registered sox compatibility shim",
    )
    return SOX_STATE


def _search_package_recursive(package_name, fname):
    """Locate ``fname`` inside an importable package directory tree."""
    module = sys.modules.get(package_name)
    if module is None:
        try:
            module = __import__(package_name)
        except Exception:  # noqa: BLE001
            return None
    pkg_file = getattr(module, "__file__", None)
    if not pkg_file:
        return None
    pkg_dir = Path(pkg_file).resolve().parent
    direct = pkg_dir / fname
    if direct.is_file():
        return direct
    try:
        for cand in pkg_dir.rglob(fname):
            if cand.is_file():
                return cand
    except Exception:  # noqa: BLE001
        return None
    return None


def _install_pooch_shim():
    """Register a functional ``pooch`` compatibility module if real pooch is absent.

    librosa imports ``pooch`` at module level purely for its optional download helper; the
    numeric resources used during TTS decoding (mel filters, interval tables, BOCL data) are all
    shipped inside the librosa package.  The shim therefore exposes a cache directory helper and a
    ``retrieve`` that searches the librosa package before refusing, so imports succeed and any
    genuine download attempt fails loudly with the symbol name.
    """
    if POOCH_STATE["installed"] or POOCH_STATE["reason"].startswith("real"):
        return POOCH_STATE
    if "pooch" in sys.modules and not getattr(sys.modules["pooch"], "_SHIM", False):
        POOCH_STATE.update(installed=False, reason="already importable (sys.modules)")
        return POOCH_STATE
    try:
        import pooch as _real_pooch  # noqa: F401

        POOCH_STATE.update(installed=False, reason="real pooch is available")
        return POOCH_STATE
    except Exception as exc:  # noqa: BLE001
        trigger = f"{type(exc).__name__}: {exc}"

    def _note(where):
        if where not in POOCH_STATE["used_at_runtime"]:
            POOCH_STATE["used_at_runtime"].append(where)

    def _os_cache(appname="pooch", *args, **kwargs):
        _note("os_cache")
        root = Path(tempfile.gettempdir()) / "librosa_offline_cache" / str(appname)
        root.mkdir(parents=True, exist_ok=True)
        return str(root)

    def _retrieve(url=None, known_hash=None, fname=None, path=None, processor=None,
                  downloader=None, progressbar=False, **kwargs):
        _note("retrieve")
        names = []
        if fname:
            names = [fname] if isinstance(fname, str) else list(fname)
        elif isinstance(url, str):
            names = [url.rsplit("/", 1)[-1].split("?")[0]]
        for name in names:
            found = _search_package_recursive("librosa", name)
            if found:
                if processor is not None:
                    return processor(str(found))
                return str(found)
        # No bundled copy: refuse instead of pretending a download succeeded.
        detail = f"url={url!r} fname={fname!r}"
        raise RuntimeError(
            "pooch compatibility shim: retrieve() was called for a resource that is not bundled "
            f"inside the librosa package ({detail}); the offline container has no network access"
        )

    class _PoochShim:
        """Stand-in for ``pooch.Pooch`` used by librosa's download helpers."""

        def __init__(self, path=None, base_url=None, registry=None, urls=None):
            self.path = path or _os_cache("librosa")
            self.registry = registry or {}
            self.base_url = base_url
            self.urls = urls or {}

        def fetch(self, fname, *args, **kwargs):
            _note("Pooch.fetch")
            return _retrieve(fname=fname, path=self.path, **kwargs)

        def load_registry(self, *args, **kwargs):
            _note("Pooch.load_registry")

        def __getattr__(self, item):
            if item.startswith("_"):
                raise AttributeError(item)
            _note(f"Pooch.{item}")
            raise AttributeError(f"pooch shim Pooch has no attribute '{item}'")

    def _create(path=None, *args, **kwargs):
        _note("create")
        if path is None:
            path = _os_cache("librosa")
        Path(path).mkdir(parents=True, exist_ok=True)
        return _PoochShim(path=path)

    module = types.ModuleType("pooch")
    module.__doc__ = (
        "Offline compatibility shim for pooch, installed because the container lacks the real "
        "package.  Provides os_cache/create plus a retrieve that resolves bundled librosa "
        "resources and refuses anything that would need network access."
    )
    module.__version__ = "0.0.0+offline-shim"
    module.retrieve = _retrieve
    module.os_cache = _os_cache
    module.create = _create
    module.Pooch = _PoochShim
    module._SHIM = True
    module._SHIM_TRIGGER = trigger

    def _module_getattr(name):
        if name.startswith("__"):
            raise AttributeError(name)
        _note(f"pooch.{name}")
        raise AttributeError(f"pooch compatibility shim has no attribute '{name}'")

    module.__getattr__ = _module_getattr
    sys.modules["pooch"] = module
    POOCH_STATE.update(
        installed=True,
        reason=f"pooch unavailable ({trigger}); registered pooch compatibility shim",
    )
    return POOCH_STATE


def _install_offline_shims():
    _install_huggingface_hub_version_shim()
    _install_sox_shim()
    _install_pooch_shim()
    return {
        "huggingface_hub_version": dict(HFHUB_STATE),
        "sox": dict(SOX_STATE),
        "pooch": dict(POOCH_STATE),
    }


# --------------------------------------------------------------------------- helpers
def sha256_file(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def safe_name(value) -> str:
    keep = "-_."
    out = "".join(ch if (ch.isalnum() or ch in keep) else "_" for ch in str(value))
    out = out.strip("_")
    return out or "item"


def normalize_language(value) -> str:
    if value is None:
        return "English"
    text = str(value).strip()
    return LANGUAGE_ALIASES.get(text.lower(), text or "English")


def read_wav(path):
    """Decode a WAV into (float32 mono numpy array, sample_rate)."""
    target = str(path)
    try:
        import soundfile as sf  # type: ignore

        data, sr = sf.read(target, dtype="float32", always_2d=False)
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.mean(axis=1).astype(np.float32)
        return np.ascontiguousarray(arr, dtype=np.float32), int(sr)
    except ImportError:
        pass
    import torchaudio  # type: ignore

    wav, sr = torchaudio.load(target)
    if wav.dim() > 1:
        wav = wav.mean(dim=0)
    return np.ascontiguousarray(wav.numpy().astype(np.float32)), int(sr)


def write_wav(path, wav, sr) -> str:
    """Write mono float audio as a 16-bit PCM WAV; never writes silent/non-finite audio."""
    arr = np.asarray(wav, dtype=np.float32)
    if arr.size == 0:
        raise ValueError("refusing to write an empty waveform")
    if not np.isfinite(arr).all():
        raise ValueError("refusing to write non-finite audio samples")
    if float(np.max(np.abs(arr))) <= 0.0:
        raise ValueError("refusing to write all-zero (silent) audio")
    clipped = np.clip(arr, -1.0, 1.0).astype(np.float32)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import soundfile as sf  # type: ignore

        sf.write(str(path), clipped, int(sr), subtype="PCM_16")
        return "soundfile:PCM_16"
    except ImportError:
        pass
    import torch
    import torchaudio  # type: ignore

    torchaudio.save(str(path), torch.from_numpy(clipped)[None, :], int(sr))
    return "torchaudio"


# --------------------------------------------------------------------------- input contract
def load_requests(path):
    reqs = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"requests.jsonl line {lineno} is not valid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"requests.jsonl line {lineno} is not a JSON object")
            rid = None
            for key in ("id", "utterance_id", "request_id", "name", "key"):
                if obj.get(key) is not None:
                    rid = str(obj[key])
                    break
            if not rid:
                rid = f"request_{lineno:04d}"
            text = None
            for key in ("text", "target_text", "target", "sentence", "prompt"):
                if isinstance(obj.get(key), str) and obj[key].strip():
                    text = obj[key]
                    break
            if not text:
                raise ValueError(f"request '{rid}' (line {lineno}) has no non-empty text field")
            language = "English"
            for key in ("language", "lang", "language_id"):
                if obj.get(key):
                    language = normalize_language(obj[key])
                    break
            reqs.append({"id": rid, "text": text, "language": language, "raw": obj})
    if not reqs:
        raise ValueError("requests.jsonl contains no requests")
    return reqs


def check_inputs(indir: Path, model_path: Path, need_model: bool = True):
    """Inspect the frozen input contract.  Returns (missing_items, info)."""
    missing = []
    info = {"input_dir": str(indir), "files": {}, "manifest": None, "requests": [], "reference_text": ""}

    if not indir.is_dir():
        missing.append(f"input directory not found: {indir}")
        return missing, info

    manifest = None
    manifest_path = indir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            info["manifest"] = {"path": str(manifest_path), "sha256": sha256_file(manifest_path)}
        except Exception as exc:  # noqa: BLE001
            missing.append(f"manifest.json is unreadable: {type(exc).__name__}: {exc}")

    for name in REQUIRED_INPUT_FILES:
        path = indir / name
        if not path.is_file():
            missing.append(f"required input file missing: {path}")
            continue
        digest = sha256_file(path)
        record = {"path": str(path), "bytes": int(path.stat().st_size), "sha256": digest}
        expected = None
        if isinstance(manifest, dict) and isinstance(manifest.get("files"), dict):
            expected = manifest["files"].get(name)
        record["expected_sha256"] = expected
        record["sha256_matches_manifest"] = (expected == digest) if expected else None
        if expected and expected != digest:
            missing.append(f"sha256 mismatch for {path}: expected {expected}, got {digest}")
        info["files"][name] = record

    ref_wav = indir / "reference.wav"
    if ref_wav.is_file():
        try:
            ref_np, ref_sr = read_wav(ref_wav)
            info["files"]["reference.wav"].update(
                {
                    "decoded_sample_rate": int(ref_sr),
                    "decoded_samples": int(ref_np.size),
                    "decoded_duration_s": round(float(ref_np.size) / float(ref_sr), 6),
                    "decoded_finite": bool(np.isfinite(ref_np).all()),
                    "decoded_peak": float(np.max(np.abs(ref_np))) if ref_np.size else 0.0,
                }
            )
            if ref_np.size == 0 or not np.isfinite(ref_np).all() or float(np.max(np.abs(ref_np))) <= 0.0:
                missing.append(f"reference.wav does not decode to finite non-silent audio: {ref_wav}")
        except Exception as exc:  # noqa: BLE001
            missing.append(f"reference.wav cannot be decoded: {type(exc).__name__}: {exc}")

    ref_text_path = indir / "reference_text.txt"
    if ref_text_path.is_file():
        try:
            ref_text = ref_text_path.read_text(encoding="utf-8").strip()
            info["reference_text"] = ref_text
            if not ref_text:
                missing.append(f"reference_text.txt is empty: {ref_text_path}")
        except Exception as exc:  # noqa: BLE001
            missing.append(f"reference_text.txt is unreadable: {type(exc).__name__}: {exc}")

    req_path = indir / "requests.jsonl"
    if req_path.is_file():
        try:
            reqs = load_requests(req_path)
            info["requests"] = reqs
            info["request_count"] = len(reqs)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"requests.jsonl is invalid: {type(exc).__name__}: {exc}")

    if need_model:
        mp = Path(model_path)
        minfo = {"path": str(mp), "repo": MODEL_ID, "revision": MODEL_REVISION}
        if not mp.is_dir():
            missing.append(f"model directory not found: {mp}")
        else:
            try:
                names = sorted(p.name for p in mp.iterdir())
                minfo["file_count"] = len(names)
                minfo["files_head"] = names[:40]
                weights = [n for n in names if n.endswith((".safetensors", ".bin", ".pt", ".ckpt"))]
                minfo["weight_files"] = weights[:10]
                if not (mp / "config.json").is_file():
                    missing.append(f"model config.json missing in {mp}")
                if not weights:
                    missing.append(f"no model weight files found in {mp}")
            except Exception as exc:  # noqa: BLE001
                missing.append(f"model directory unreadable: {type(exc).__name__}: {exc}")
        info["model"] = minfo
    return missing, info


# --------------------------------------------------------------------------- model API adapter
def _map_kwargs(fn, canonical):
    """Map canonical argument names onto the real callable signature (no invention)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {key: value for key, _alts, value in canonical}, {key: key for key, _a, _v in canonical}
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    kwargs, mapping = {}, {}
    for key, aliases, value in canonical:
        chosen = key if key in params else next((a for a in aliases if a in params), None)
        if chosen is None:
            if not has_var_kw:
                continue
            chosen = key
        kwargs[chosen] = value
        mapping[key] = chosen
    return kwargs, mapping


def import_qwen_tts():
    """Import the official qwen_tts package with offline compatibility shims installed first."""
    _install_offline_shims()
    try:
        from qwen_tts import Qwen3TTSModel  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"qwen_tts could not be imported ({exc}); the official Qwen3-TTS stack is required and "
            "no substitute TTS backend will be used"
        ) from exc
    return Qwen3TTSModel


def load_model(model_path: str, device: str = "cuda:0"):
    """Load the official qwen_tts Qwen3TTSModel on CUDA (bf16 preferred)."""
    import torch

    Qwen3TTSModel = import_qwen_tts()

    attempts = (
        {"device_map": device, "dtype": torch.bfloat16},
        {"device_map": device, "torch_dtype": torch.bfloat16},
        {"device_map": device},
    )
    last_error = None
    for kwargs in attempts:
        try:
            model = Qwen3TTSModel.from_pretrained(model_path, **kwargs)
        except TypeError as exc:  # signature mismatch -> try the next documented form
            last_error = exc
            continue
        try:
            model.eval()
        except Exception:  # noqa: BLE001 - eval() is best-effort
            pass
        placement = "unknown"
        try:
            param = next(model.parameters())
            placement = str(param.device)
        except Exception:  # noqa: BLE001
            placement = str(getattr(model, "device", "unknown"))
        if "cuda" not in placement and placement != "unknown":
            raise RuntimeError(f"model was placed on {placement}, but this task requires CUDA")
        return model, {k: str(v) for k, v in kwargs.items()}, placement
    raise RuntimeError(f"could not load Qwen3TTSModel from {model_path}: {last_error}")


def synthesize(model, req, ref_arg, ref_text, x_vector_only_mode, generator=None):
    fn = getattr(model, "generate_voice_clone", None)
    if not callable(fn):
        raise RuntimeError(
            "the loaded qwen_tts model does not expose generate_voice_clone; this task requires "
            "reference voice cloning and refuses to substitute a non-cloning TTS backend"
        )
    canonical = [
        ("text", ("target_text", "input_text", "sentence"), req["text"]),
        ("language", ("lang", "language_id"), req["language"]),
        ("ref_audio", ("reference_audio", "speaker_audio", "audio", "ref_audio_path", "reference_wav"), ref_arg),
        ("ref_text", ("reference_text", "ref_transcript"), ref_text),
        ("x_vector_only_mode", ("xvector_only_mode", "x_vector_only", "use_xvector_only"), bool(x_vector_only_mode)),
    ]
    kwargs, mapping = _map_kwargs(fn, canonical)
    if generator is not None:
        try:
            if "generator" in inspect.signature(fn).parameters:
                kwargs["generator"] = generator
                mapping["generator"] = "generator"
        except (TypeError, ValueError):
            pass
    return fn(**kwargs), mapping


def generate_for_request(model, req, ref_path, ref_np, ref_sr, ref_text, generator=None):
    """Try the reference recording as a path first, then as an in-memory (array, sr) pair."""
    attempts = ((str(ref_path), "path"), ((ref_np, int(ref_sr)), "array+sample_rate"))
    errors = []
    for ref_arg, form in attempts:
        try:
            result, mapping = synthesize(
                model, req, ref_arg, ref_text, X_VECTOR_ONLY_MODE, generator=generator
            )
            return {"result": result, "api_mapping": mapping, "reference_input_form": form}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{form}: {type(exc).__name__}: {exc}")
    raise RuntimeError("generate_voice_clone failed for every reference input form: " + " | ".join(errors))


def _looks_like_audio(value) -> bool:
    if isinstance(value, np.ndarray):
        return True
    if isinstance(value, (list, tuple)):
        return len(value) > 0 and _looks_like_audio(value[0])
    try:
        import torch

        return isinstance(value, torch.Tensor)
    except Exception:  # noqa: BLE001
        return False


def _to_mono_float(value) -> np.ndarray:
    try:
        import torch

        if isinstance(value, torch.Tensor):
            arr = value.detach().to("cpu").float().numpy()
        else:
            arr = np.asarray(value, dtype=np.float32)
    except ImportError:
        arr = np.asarray(value, dtype=np.float32)
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim == 0:
        arr = arr.reshape(1)
    if arr.ndim == 2:
        if arr.shape[0] == 1:
            arr = arr[0]
        elif arr.shape[1] == 1:
            arr = arr[:, 0]
        else:
            arr = arr.mean(axis=0)
    elif arr.ndim > 2:
        arr = arr.reshape(-1)
    return np.ascontiguousarray(arr.astype(np.float32))


def extract_audio(result):
    """Normalise the many legal return shapes of the official API into (float32 mono, sr|None)."""
    sr, wav = None, None
    if isinstance(result, dict):
        for key in ("wavs", "audio", "waveform", "wav", "samples", "output"):
            if key in result:
                wav = result[key]
                break
        for key in ("sample_rate", "sr", "sampling_rate", "rate"):
            if key in result:
                try:
                    sr = int(result[key])
                except (TypeError, ValueError):
                    sr = None
                break
    elif isinstance(result, (tuple, list)):
        items = list(result)
        for item in items:
            if sr is None and isinstance(item, (int, float)) and not isinstance(item, bool) and float(item) >= 4000:
                sr = int(item)
        for item in items:
            if _looks_like_audio(item):
                wav = item
                break
    else:
        wav = result
    if wav is None:
        raise RuntimeError(f"could not locate a waveform in model output of type {type(result).__name__}")
    depth = 0
    while isinstance(wav, (list, tuple)) and len(wav) > 0 and _looks_like_audio(wav[0]) and depth < 4:
        wav = wav[0]
        depth += 1
    return _to_mono_float(wav), sr


def _search_sample_rate(node):
    if isinstance(node, dict):
        for key in ("sample_rate", "sampling_rate", "audio_sample_rate"):
            value = node.get(key)
            if isinstance(value, int) and value > 0:
                return value
        for value in node.values():
            found = _search_sample_rate(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _search_sample_rate(value)
            if found:
                return found
    return None


def resolve_sample_rate(sr, model, model_dir):
    if isinstance(sr, int) and sr > 0:
        return sr, "model_return"
    try:
        found = _search_sample_rate(getattr(model, "config", None))
        if found:
            return found, "model_config"
        inner = getattr(model, "model", None)
        found = _search_sample_rate(getattr(inner, "config", None))
        if found:
            return found, "model_inner_config"
    except Exception:  # noqa: BLE001
        pass
    config_path = Path(model_dir) / "config.json"
    if config_path.is_file():
        try:
            found = _search_sample_rate(json.loads(config_path.read_text(encoding="utf-8")))
            if found:
                return found, "model_config_json"
        except Exception:  # noqa: BLE001
            pass
    raise RuntimeError("could not determine the model's native output sample rate")


# --------------------------------------------------------------------------- commands
def cmd_doctor(args) -> int:
    # Install all offline shims BEFORE touching qwen_tts/transformers imports.
    _install_offline_shims()

    report = {
        "task_id": TASK_ID,
        "command": "doctor",
        "scale": SCALE,
        "input": str(Path(args.input)),
        "model_path": str(args.model),
        "model_repo": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "checks": [],
        "missing": [],
    }

    def add(name, ok, detail=""):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)})
        if not ok:
            report["missing"].append(f"{name}: {detail}")

    missing, info = check_inputs(Path(args.input), Path(args.model), need_model=True)
    report["inputs"] = info
    add("input_and_model_contract", not missing, "; ".join(missing) if missing else "all required files present and consistent")

    try:
        import torch

        add("dependency_torch", True, f"torch {torch.__version__}")
        cuda_ok = bool(torch.cuda.is_available())
        detail = "torch.cuda.is_available() == False"
        if cuda_ok:
            detail = f"{torch.cuda.get_device_name(0)} capability={torch.cuda.get_device_capability(0)}"
            try:
                detail += f" bf16_ok={bool(torch.cuda.is_bf16_supported())}"
            except Exception:  # noqa: BLE001
                pass
        add("dependency_cuda", cuda_ok, detail)
    except Exception as exc:  # noqa: BLE001
        add("dependency_torch", False, f"{type(exc).__name__}: {exc}")
        add("dependency_cuda", False, "torch unavailable")

    try:
        import transformers  # type: ignore

        add("dependency_transformers", True, f"transformers {transformers.__version__}")
    except Exception as exc:  # noqa: BLE001
        add("dependency_transformers", False, f"{type(exc).__name__}: {exc}")

    report["compatibility"] = _install_offline_shims()
    add("compatibility_huggingface_hub_version", True,
        f"patched={HFHUB_STATE['patched']}; real={HFHUB_STATE['real_version']!r}; reported={HFHUB_STATE['reported_version']!r}; {HFHUB_STATE['reason']}")
    add("compatibility_sox", True, f"installed={SOX_STATE['installed']}; {SOX_STATE['reason']}")
    add("compatibility_pooch", True, f"installed={POOCH_STATE['installed']}; {POOCH_STATE['reason']}")

    try:
        Qwen3TTSModel = import_qwen_tts()

        has_clone = callable(getattr(Qwen3TTSModel, "generate_voice_clone", None))
        add("dependency_qwen_tts", True, "Qwen3TTSModel imported")
        add("api_generate_voice_clone", has_clone, "Qwen3TTSModel.generate_voice_clone must exist")
    except Exception as exc:  # noqa: BLE001
        add("dependency_qwen_tts", False, f"{type(exc).__name__}: {exc}")
        add("api_generate_voice_clone", False, "qwen_tts import failed")
    finally:
        report["compatibility"] = {
            "huggingface_hub_version": dict(HFHUB_STATE),
            "sox": dict(SOX_STATE),
            "pooch": dict(POOCH_STATE),
        }

    writer = None
    try:
        import soundfile  # type: ignore  # noqa: F401

        writer = "soundfile"
    except Exception:  # noqa: BLE001
        try:
            import torchaudio  # type: ignore  # noqa: F401

            writer = "torchaudio"
        except Exception:  # noqa: BLE001
            writer = None
    add("dependency_wav_io", writer is not None, f"writer={writer}")

    report["ok"] = not report["missing"]
    report["status"] = "ready" if report["ok"] else "missing_requirements"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 78


def cmd_run(args) -> int:
    wall_start = time.perf_counter()
    _install_offline_shims()
    import torch

    if not torch.cuda.is_available():
        print(
            json.dumps(
                {"task_id": TASK_ID, "error": "CUDA is required for this task but is unavailable"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 78

    indir = Path(args.input)
    outdir = Path(args.output)
    model_dir = Path(args.model)

    missing, info = check_inputs(indir, model_dir, need_model=True)
    if missing:
        print(
            json.dumps(
                {"task_id": TASK_ID, "error": "missing prerequisites", "missing": missing},
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 78
    reqs = info["requests"]
    ref_text = info["reference_text"]
    ref_audio_path = Path(info["files"]["reference.wav"]["path"]).resolve()

    outdir.mkdir(parents=True, exist_ok=True)
    speech_dir = outdir / "speech"
    speech_dir.mkdir(parents=True, exist_ok=True)

    seed = int(args.seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

    ref_np, ref_sr = read_wav(ref_audio_path)

    torch.cuda.synchronize()
    load_start = time.perf_counter()
    model, load_kwargs, placement = load_model(str(model_dir), device=args.device)
    torch.cuda.synchronize()
    model_load_s = time.perf_counter() - load_start

    generator = None
    try:
        generator = torch.Generator(device=args.device).manual_seed(seed)
    except Exception:  # noqa: BLE001
        generator = None

    records, timings = [], []
    for req in reqs:
        torch.cuda.synchronize()
        req_start = time.perf_counter()
        produced = generate_for_request(
            model, req, ref_audio_path, ref_np, ref_sr, ref_text, generator=generator
        )
        torch.cuda.synchronize()
        req_seconds = time.perf_counter() - req_start

        wav, sr = extract_audio(produced["result"])
        sr, sr_source = resolve_sample_rate(sr, model, model_dir)
        wav = np.asarray(wav, dtype=np.float32)
        if wav.size == 0:
            raise RuntimeError(f"empty waveform produced for request {req['id']}")
        if not np.isfinite(wav).all():
            raise RuntimeError(f"non-finite samples produced for request {req['id']}")
        peak = float(np.max(np.abs(wav)))
        if peak <= 0.0:
            raise RuntimeError(f"silent output produced for request {req['id']}")

        rel_path = f"speech/{safe_name(req['id'])}.wav"
        wav_path = outdir / rel_path
        overwrote = wav_path.exists()
        writer = write_wav(wav_path, wav, sr)

        back, back_sr = read_wav(wav_path)
        if int(back_sr) != int(sr):
            raise RuntimeError(f"sample rate changed after writing {wav_path}: {back_sr} != {sr}")
        if back.size == 0 or not np.isfinite(back).all():
            raise RuntimeError(f"written audio is empty or non-finite: {wav_path}")
        back_peak = float(np.max(np.abs(back)))
        if back_peak <= 0.0:
            raise RuntimeError(f"written audio is silent: {wav_path}")

        duration = float(back.size) / float(back_sr)
        records.append(
            {
                "id": req["id"],
                "text": req["text"],
                "language": req["language"],
                "wav": rel_path,
                "sample_rate": int(back_sr),
                "num_samples": int(back.size),
                "duration_s": round(duration, 6),
                "sha256": sha256_file(wav_path),
                "bytes": int(wav_path.stat().st_size),
                "peak_abs": back_peak,
                "finite": True,
                "non_silent": True,
                "writer": writer,
                "sample_rate_source": sr_source,
                "reference_wav": str(ref_audio_path),
                "reference_text": ref_text,
                "x_vector_only_mode": X_VECTOR_ONLY_MODE,
                "seed": seed,
                "api": "generate_voice_clone",
                "api_argument_names": produced["api_mapping"],
                "reference_input_form": produced["reference_input_form"],
                "overwrote_existing_file": overwrote,
            }
        )
        timings.append(
            {
                "id": req["id"],
                "gpu_synchronized_seconds": round(req_seconds, 6),
                "audio_duration_s": round(duration, 6),
            }
        )

    index_path = outdir / "index.jsonl"
    with open(index_path, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    rng_info = None
    try:
        rng_path = outdir / "rng_state.pt"
        torch.save(
            {"seed": seed, "torch_rng_state": torch.get_rng_state(), "cuda_rng_state_all": torch.cuda.get_rng_state_all()},
            rng_path,
        )
        rng_info = {"path": "rng_state.pt", "sha256": sha256_file(rng_path)}
    except Exception as exc:  # noqa: BLE001
        rng_info = {"error": f"{type(exc).__name__}: {exc}"}

    torch.cuda.synchronize()
    total_wall = time.perf_counter() - wall_start
    run_report = {
        "task_id": TASK_ID,
        "scale": SCALE,
        "status": "ok",
        "command": "run",
        "model": {
            "repo": MODEL_ID,
            "revision": MODEL_REVISION,
            "path": str(model_dir),
            "placement": placement,
            "load_kwargs": load_kwargs,
            "api": "qwen_tts.Qwen3TTSModel.generate_voice_clone",
        },
        "inputs": {
            "input_dir": str(indir),
            "files": info["files"],
            "manifest": info.get("manifest"),
            "reference_text": ref_text,
            "reference_text_chars": len(ref_text),
            "request_count": len(reqs),
        },
        "parameters": {
            "seed": seed,
            "seed_overridable": True,
            "x_vector_only_mode": X_VECTOR_ONLY_MODE,
            "device": args.device,
            "dtype": "bfloat16",
            "language_default": "English",
        },
        "environment": {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "capability": list(torch.cuda.get_device_capability(0)),
        },
        "compatibility": {
            "huggingface_hub_version": dict(HFHUB_STATE),
            "sox": dict(SOX_STATE),
            "pooch": dict(POOCH_STATE),
        },
        "outputs": records,
        "timings": {
            "model_load_gpu_synchronized_s": round(model_load_s, 6),
            "per_request": timings,
            "generation_gpu_synchronized_s": round(sum(t["gpu_synchronized_seconds"] for t in timings), 6),
            "total_wall_s": round(total_wall, 6),
        },
        "memory": {
            "peak_cuda_allocated_gib": round(torch.cuda.max_memory_allocated() / (1024 ** 3), 4),
            "peak_cuda_reserved_gib": round(torch.cuda.max_memory_reserved() / (1024 ** 3), 4),
        },
        "rng_state": rng_info,
        "index_jsonl": "index.jsonl",
    }
    run_path = outdir / "run.json"
    run_path.write_text(json.dumps(run_report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"status": "ok", "outputs": len(records), "index": str(index_path), "run": str(run_path)}, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution/main.py",
        description=(
            "GPUv1-C09 (debug): clone the voice of input/reference.wav with Qwen3-TTS 0.6B Base "
            "and synthesise every text request in input/requests.jsonl on CUDA."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", help="inspect required inputs/dependencies without running models")
    doctor.add_argument("--input", required=True, help="input directory containing the frozen task files")
    doctor.add_argument("--model", default=DEFAULT_MODEL_PATH, help="local Qwen3-TTS Base model directory")

    run = sub.add_parser("run", help="generate reference-cloned speech for every request")
    run.add_argument("--input", required=True, help="input directory containing the frozen task files")
    run.add_argument("--output", required=True, help="output directory for speech/, index.jsonl and run.json")
    run.add_argument("--model", default=DEFAULT_MODEL_PATH, help="local Qwen3-TTS Base model directory")
    run.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (override for later requests)")
    run.add_argument("--device", default="cuda:0", help="CUDA device string")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
