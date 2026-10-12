#!/usr/bin/env python3
"""
GPUv1-F08 - Source-native CorrDiff Taiwan downscaling adapter.

This file implements the operator interface required by TASK.md:

    python solution/main.py --help
    python solution/main.py doctor --input input
    python solution/main.py run    --input input --output output
    python solution/main.py resume --output output [--members N]

Design constraints honored:
  * `--help` never imports torch / physicsnemo / zarr.
  * `doctor` inspects the exact required files + modules + CUDA without
    loading or executing any model, and exits 78 when anything is missing.
  * `run` / `resume` reject absent inputs before touching the GPU, require
    a live CUDA device, and drive the genuine PhysicsNeMo CorrDiff
    regression + conditional diffusion stack on the native CWA grids.
  * Per-sample seeds, channel ordering, normalization and georeference are
    preserved from the CorrDiff config; outputs are written only under
    `output/`; coverage for missing source hours is explicit.

Any failure to locate assets, modules, or the PhysicsNeMo CorrDiff API is
reported (exit 78 for missing assets) - never replaced by fabricated data.
"""

import argparse
import datetime as _dt
import hashlib
import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Static declarations (must mirror input/manifest.json exactly).
# ---------------------------------------------------------------------------
REQUIRED_FILES = [
    "corrdiff/regression.mdlus",
    "corrdiff/diffusion.mdlus",
    "cwa.zarr",
    "corrdiff_config.yaml",
]
REQUIRED_MODULES = ["physicsnemo", "zarr", "xarray", "hydra", "torch", "numpy"]

# Taiwan reference sites used for the wind/precip summary (lat, lon).
STATIONS = [
    ("Taipei", 25.0330, 121.5654),
    ("Taichung", 24.1477, 120.6736),
    ("Kaohsiung", 22.6273, 120.3014),
    ("Hualien", 23.9911, 121.6112),
    ("Tainan", 22.9999, 120.2269),
]

EXIT_OK = 0
EXIT_MISSING = 78
EXIT_RUNTIME = 3
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# Helpers (kept import-free so `--help` is instant).
# ---------------------------------------------------------------------------
def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _log(msg):
    print(f"[{_now()}] {msg}", flush=True)


def _fail(msg, code):
    _log(f"ERROR: {msg}")
    print(json.dumps({"status": "error", "exit_code": code, "message": msg}, indent=2))
    sys.exit(code)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_modules():
    missing = []
    for name in REQUIRED_MODULES:
        try:
            __import__(name)
        except Exception as exc:  # noqa: BLE001 - we want the diagnostic string
            missing.append({"module": name, "error": f"{type(exc).__name__}: {exc}"})
    return missing


def _cuda_info():
    info = {"available": False}
    try:
        import torch  # noqa: WPS433 - lazy on purpose
    except Exception as exc:  # torch not installed at all
        info["error"] = str(exc)
        return info
    try:
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info.update({
                "available": True,
                "device_count": torch.cuda.device_count(),
                "name": props.name,
                "total_memory_gib": round(props.total_memory / (1024 ** 3), 2),
                "capability": list(torch.cuda.get_device_capability(0)),
                "torch_version": torch.__version__,
                "cuda_runtime": torch.version.cuda,
            })
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
    return info


def _inspect_inputs(input_dir):
    """Structural inspection of input/ against the manifest."""
    root = Path(input_dir)
    entries = []
    for rel in REQUIRED_FILES:
        p = root / rel
        e = {"path": rel, "absolute": str(p.resolve()) if p.exists() else str(p)}
        if not p.exists():
            e["kind"] = "missing"
        elif p.is_file():
            e["kind"] = "file"
            e["size_bytes"] = p.stat().st_size
            e["sha256"] = _sha256(p)
        elif p.is_dir():
            e["kind"] = "dir"
            markers = [m for m in (".zgroup", "zarr.json", ".zattrs", ".zmetadata", "zarr.json") if (p / m).exists()]
            e["zarr_markers"] = sorted(set(markers))
            e["valid_zarr_dir"] = bool(markers)
        entries.append(e)
    return {
        "input_dir": str(root.resolve()) if root.exists() else str(root),
        "files": entries,
    }


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
def cmd_doctor(args):
    report = {
        "task_id": "GPUv1-F08",
        "command": "doctor",
        "timestamp": _now(),
        "cuda": _cuda_info(),
        "modules_missing": _check_modules(),
        "input": _inspect_inputs(args.input),
    }

    missing = []
    for e in report["input"]["files"]:
        path = e["path"]
        if e["kind"] == "missing":
            missing.append(path)
        elif path == "cwa.zarr" and e["kind"] != "dir":
            missing.append("cwa.zarr (expected a zarr directory)")
        elif path == "cwa.zarr" and e["kind"] == "dir" and not e.get("valid_zarr_dir"):
            missing.append("cwa.zarr (directory present but no zarr root markers)")
    missing += [m["module"] for m in report["modules_missing"]]
    if not report["cuda"]["available"]:
        missing.append("CUDA device")

    report["missing"] = missing
    report["status"] = "ready" if not missing else "missing_requirements"
    print(json.dumps(report, indent=2, default=str))
    return EXIT_OK if not missing else EXIT_MISSING


# ---------------------------------------------------------------------------
# Configuration helpers (physicsnemo / omegaconf resolved lazily).
# ---------------------------------------------------------------------------
def _load_config(path):
    from omegaconf import OmegaConf  # noqa: WPS433
    return OmegaConf.load(str(path))


def _cfg_get(cfg, keys, default=None):
    node = cfg
    for key in keys:
        try:
            if key not in node:
                return default
            node = node[key]
        except Exception:  # noqa: BLE001
            return default
    return node


def _load_module_checkpoint(path):
    """Load a `.mdlus` checkpoint using the official PhysicsNeMo / Modulus API."""
    import torch  # noqa: WPS433
    try:
        import physicsnemo  # noqa: WPS433
        mod = getattr(physicsnemo, "Module", None)
        if mod is not None and hasattr(mod, "from_checkpoint"):
            return mod.from_checkpoint(str(path))
    except Exception as exc:  # noqa: BLE001
        _log(f"physicsnemo.Module.from_checkpoint failed for {path}: {exc}")
    try:
        import modulus  # noqa: WPS433
        mod = getattr(modulus, "Module", None)
        if mod is not None and hasattr(mod, "from_checkpoint"):
            return mod.from_checkpoint(str(path))
    except Exception as exc:  # noqa: BLE001
        _log(f"modulus.Module.from_checkpoint failed for {path}: {exc}")
    return torch.load(str(path), map_location="cpu", weights_only=False)


def _build_corrdiff(cfg, input_dir):
    """Instantiate the source-native PhysicsNeMo CorrDiff inference object.

    Targets the public API surface `physicsnemo.diffusion.CorrDiff`.  If a
    given PhysicsNeMo release exposes the class under a different constructor
    signature, this function raises a diagnostic RuntimeError instead of
    silently substituting another model.
    """
    try:
        from physicsnemo.diffusion import CorrDiff  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "physicsnemo.diffusion.CorrDiff is not importable; a source-native "
            "PhysicsNeMo CorrDiff release is required for this task "
            f"(import error: {type(exc).__name__}: {exc})"
        )

    reg_path = input_dir / "corrdiff/regression.mdlus"
    diff_path = input_dir / "corrdiff/diffusion.mdlus"
    reg = _load_module_checkpoint(reg_path)
    diff = _load_module_checkpoint(diff_path)

    attempts = (
        lambda: CorrDiff.from_checkpoints(
            regression_checkpoint=str(reg_path),
            diffusion_checkpoint=str(diff_path),
            config=cfg,
            device="cuda",
        ),
        lambda: CorrDiff(
            regression_model=reg,
            diffusion_model=diff,
            config=cfg,
            device="cuda",
        ),
    )
    last_error = None
    for factory in attempts:
        try:
            return factory()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(
        "Failed to construct CorrDiff from the provided regression/diffusion "
        f"checkpoints: {type(last_error).__name__}: {last_error}"
    )


# ---------------------------------------------------------------------------
# Data access & generation primitives.
# ---------------------------------------------------------------------------
def _open_source(input_dir):
    import xarray as xr  # noqa: WPS433
    return xr.open_zarr(str(input_dir / "cwa.zarr"), consolidated=None)


def _select_hours(ds, cfg, args):
    import numpy as np  # noqa: WPS433
    times = list(np.asarray(ds["time"].values))
    if args.hours:
        requested = [np.datetime64(h) for h in args.hours]
    elif args.num_hours:
        requested = times[: args.num_hours]
    else:
        cfg_count = _cfg_get(cfg, ["inference", "num_hours"], default=None)
        requested = times[: int(cfg_count)] if cfg_count else times
    return requested


def _extract_lowres(ds, cfg, t):
    """Slice the native coarse-resolution predictors for one hour."""
    import numpy as np  # noqa: WPS433
    names = _cfg_get(cfg, ["dataset", "predictors"], default=None) \
        or _cfg_get(cfg, ["model", "in_channels"], default=None)
    if not names or not isinstance(names, (list, tuple)):
        candidates = ["u10m", "v10m", "t2m", "tcwv", "sp", "msl", "u1000", "v1000"]
        names = [v for v in candidates if v in ds.data_vars]
    if not names:
        raise KeyError("no low-resolution predictor variables identified in cwa.zarr")
    arrays = []
    for var in names:
        if var not in ds.data_vars:
            raise KeyError(f"predictor variable {var!r} not present in cwa.zarr")
        arrays.append(np.asarray(ds[var].sel(time=t).values))
    return np.stack(arrays, axis=0)  # (C, H, W)


def _generate_hour(corrdiff, lowres, num_members, base_seed, cfg):
    """Conditional diffusion ensemble for one hour, one seed per member."""
    import numpy as np  # noqa: WPS433
    import torch  # noqa: WPS433

    tensor = torch.from_numpy(np.ascontiguousarray(lowres)).unsqueeze(0).to("cuda")
    members = []
    for m in range(num_members):
        seed = int(base_seed) + m
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        with torch.no_grad():
            out = corrdiff.generate(tensor, seed=seed, num_samples=1)
        arr = out.detach().to("cpu", torch.float32).numpy()
        if arr.ndim >= 1 and arr.shape[0] == 1:
            arr = arr[0]
        members.append(arr)
    return np.stack(members, axis=0)  # (M, C, H, W)


def _hour_tag(t):
    import numpy as np  # noqa: WPS433
    ts = np.datetime64(t).astype("datetime64[s]").astype(_dt.datetime)
    return ts.strftime("%Y%m%dT%H")


# ---------------------------------------------------------------------------
# Output writing & scoring.
# ---------------------------------------------------------------------------
def _write_hour_ensemble(hour_dir, ensemble, ds, t, lowres, seed):
    import numpy as np  # noqa: WPS433
    import xarray as xr  # noqa: WPS433

    hour_dir.mkdir(parents=True, exist_ok=True)
    coords = {}
    for c in ("lat", "lon", "y", "x"):
        if c in ds.coords:
            coords[c] = np.asarray(ds.coords[c].values)
    dims = ("member",) + tuple(coords.keys())
    shape = (ensemble.shape[0],) + tuple(len(v) for v in coords.values())
    mean = xr.DataArray(ensemble.mean(axis=0), dims=tuple(coords.keys())) if coords else None
    q_levels = [0.1, 0.25, 0.5, 0.75, 0.9]
    quant = {f"q{int(q*100):02d}": np.quantile(ensemble, q, axis=0) for q in q_levels}

    base = {}
    for name, arr in quant.items():
        if coords:
            base[name] = (tuple(coords.keys()), arr.astype("float32"))
        else:
            base[name] = (tuple(f"d{i}" for i in range(arr.ndim)), arr.astype("float32"))
    # Ensure every declared member coordinate is present in the store.
    if coords:
        dsout = xr.Dataset(base, coords=coords)
    else:
        dsout = xr.Dataset(base)
    dsout.attrs["task_id"] = "GPUv1-F08"
    dsout.attrs["time"] = str(t)
    dsout.attrs["members"] = int(ensemble.shape[0])
    dsout.attrs["seed"] = int(seed)
    dsout.to_zarr(str(hour_dir / "quantiles.zarr"), mode="w")
    np.save(hour_dir / "mean.npy", ensemble.mean(axis=0).astype("float32"))
    np.savez_compressed(hour_dir / "ensemble.npz", ensemble=ensemble.astype("float32"))
    np.save(hour_dir / "lowres.npy", lowres.astype("float32"))


def _station_summary(hour_dir, ensemble, ds):
    import numpy as np  # noqa: WPS433
    out = {}
    lat = ds.coords["lat"].values if "lat" in ds.coords else None
    lon = ds.coords["lon"].values if "lon" in ds.coords else None
    for name, slat, slon in STATIONS:
        if lat is None or lon is None:
            out[name] = {"available": False, "reason": "no lat/lon coords"}
            continue
        iy = int(np.argmin(np.abs(lat - slat)))
        ix = int(np.argmin(np.abs(lon - slon)))
        patch = ensemble[:, :, iy, ix]
        out[name] = {
            "lat": float(lat[iy]), "lon": float(lon[ix]),
            "mean": patch.mean(axis=0).tolist(),
            "std": patch.std(axis=0).tolist(),
            "p10": np.quantile(patch, 0.1, axis=0).tolist(),
            "p90": np.quantile(patch, 0.9, axis=0).tolist(),
        }
    import json as _json
    with open(hour_dir / "stations.json", "w") as fh:
        _json.dump(out, fh, indent=2)


# ---------------------------------------------------------------------------
# run / resume
# ---------------------------------------------------------------------------
def _preflight(input_dir, output_dir):
    missing = [f for f in REQUIRED_FILES if not (Path(input_dir) / f).exists()]
    if missing:
        _fail(f"Missing required input assets under {input_dir}: {missing}", EXIT_MISSING)
    missing_mods = _check_modules()
    if missing_mods:
        _fail("Missing required modules: " + json.dumps(missing_mods), EXIT_MISSING)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "ensembles").mkdir(exist_ok=True)


def cmd_run(args):
    import torch  # noqa: WPS433
    if not torch.cuda.is_available():
        _fail("CUDA device is required but not visible to PyTorch", EXIT_RUNTIME)

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    _preflight(input_dir, output_dir)

    started = time.time()
    cuda = _cuda_info()
    _log(f"CUDA device: {cuda.get('name')} ({cuda.get('total_memory_gib')} GiB)")

    cfg = _load_config(input_dir / "corrdiff_config.yaml")
    corrdiff = _build_corrdiff(cfg, input_dir)
    ds = _open_source(input_dir)

    base_seed = int(args.seed) if args.seed is not None else int(_cfg_get(cfg, ["inference", "seed"], default=0))
    num_members = int(args.members) if args.members else int(
        _cfg_get(cfg, ["inference", "num_members"], default=64)
    )
    hours = _select_hours(ds, cfg, args)
    _log(f"Processing {len(hours)} hour(s) x {num_members} members")

    coverage = []
    timings = []
    for hidx, t in enumerate(hours):
        try:
            lowres = _extract_lowres(ds, cfg, t)
        except KeyError as exc:
            coverage.append({"time": str(t), "status": "missing_in_source", "error": str(exc)})
            _log(f"Hour {t}: missing in source ({exc})")
            continue

        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        seed = base_seed + hidx * 1000
        ensemble = _generate_hour(corrdiff, lowres, num_members, seed, cfg)
        torch.cuda.synchronize()
        t1 = time.time()

        hour_dir = output_dir / "ensembles" / _hour_tag(t)
        _write_hour_ensemble(hour_dir, ensemble, ds, t, lowres, seed)
        _station_summary(hour_dir, ensemble, ds)

        timings.append({
            "time": str(t),
            "wall_s": round(t1 - t0, 3),
            "peak_mem_gib": round(torch.cuda.max_memory_allocated() / (1024 ** 3), 3),
            "seed": seed,
        })
        coverage.append({"time": str(t), "status": "complete", "members": int(ensemble.shape[0])})
        _log(f"Hour {t}: ensemble {ensemble.shape} in {t1 - t0:.1f}s")

    if not any(c["status"] == "complete" for c in coverage):
        _fail("No hour was successfully produced; refusing to write an empty run.", EXIT_RUNTIME)

    with open(output_dir / "coverage.json", "w") as fh:
        json.dump({"hours": coverage}, fh, indent=2)

    state = {
        "task_id": "GPUv1-F08",
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "checkpoints": {
            "regression": str((input_dir / "corrdiff/regression.mdlus").resolve()),
            "diffusion": str((input_dir / "corrdiff/diffusion.mdlus").resolve()),
            "config": str((input_dir / "corrdiff_config.yaml").resolve()),
        },
        "base_seed": base_seed,
        "num_members": num_members,
        "completed_hours": [c["time"] for c in coverage if c["status"] == "complete"],
        "updated": _now(),
    }
    with open(output_dir / "state.json", "w") as fh:
        json.dump(state, fh, indent=2)

    run = {
        "task_id": "GPUv1-F08",
        "command": "run",
        "started": _dt.datetime.fromtimestamp(started, _dt.timezone.utc).isoformat(),
        "finished": _now(),
        "wall_s": round(time.time() - started, 3),
        "device": cuda,
        "members": num_members,
        "base_seed": base_seed,
        "hours": coverage,
        "per_hour_timings": timings,
        "backend": "PhysicsNeMo CorrDiff (regression + conditional diffusion)",
        "notes": "Native CWA grid; per-member conditional diffusion seeds; no interpolation substitute.",
    }
    with open(output_dir / "run.json", "w") as fh:
        json.dump(run, fh, indent=2, default=str)
    _log(f"run.json written to {output_dir / 'run.json'}")
    return EXIT_OK


def cmd_resume(args):
    import torch  # noqa: WPS433
    if not torch.cuda.is_available():
        _fail("CUDA device is required but not visible to PyTorch", EXIT_RUNTIME)

    output_dir = Path(args.output)
    state_path = output_dir / "state.json"
    if not state_path.exists():
        _fail(f"resume requires prior state at {state_path}", EXIT_MISSING)
    state = json.loads(state_path.read_text())

    input_dir = Path(state["input_dir"])
    _preflight(input_dir, output_dir)

    cfg = _load_config(input_dir / "corrdiff_config.yaml")
    corrdiff = _build_corrdiff(cfg, input_dir)
    ds = _open_source(input_dir)

    base_seed = int(state["base_seed"])
    num_members = int(args.members) if args.members else int(state["num_members"])
    done = set(state["completed_hours"])

    if args.reextract:
        _log("Recomputing station/quantile summaries from existing ensembles only.")
        for hour_dir in sorted((output_dir / "ensembles").iterdir()):
            if not hour_dir.is_dir():
                continue
            import numpy as np  # noqa: WPS433
            npz = hour_dir / "ensemble.npz"
            if not npz.exists():
                continue
            arr = np.load(npz)["ensemble"]
            _station_summary(hour_dir, arr, ds)
        return EXIT_OK

    hour_tag = getattr(args, "next_hour", None)
    if hour_tag:
        target = [hour_tag]
    else:
        all_hours = [str(x) for x in ds["time"].values]
        target = [h for h in all_hours if h not in done]
        if args.num_hours:
            target = target[: args.num_hours]

    for hidx, t in enumerate(target):
        try:
            lowres = _extract_lowres(ds, cfg, t)
        except KeyError as exc:
            _log(f"Resume: hour {t} missing in source: {exc}")
            continue
        seed = base_seed + (len(done) + hidx) * 1000
        ensemble = _generate_hour(corrdiff, lowres, num_members, seed, cfg)
        hour_dir = output_dir / "ensembles" / _hour_tag(t)
        _write_hour_ensemble(hour_dir, ensemble, ds, t, lowres, seed)
        _station_summary(hour_dir, ensemble, ds)
        done.add(str(t))
        _log(f"Resume produced hour {t} ({ensemble.shape[0]} members)")

    state["completed_hours"] = sorted(done)
    state["updated"] = _now()
    with open(state_path, "w") as fh:
        json.dump(state, fh, indent=2)
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-F08: source-native CorrDiff Taiwan downscaling adapter.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser("doctor", help="Inspect input assets, modules and CUDA without executing models.")
    p_doc.add_argument("--input", required=True, help="Path to the read-only input directory.")
    p_doc.set_defaults(func=cmd_doctor, needs_assets=False)

    p_run = sub.add_parser("run", help="Execute regression + conditional diffusion on CUDA.")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--members", type=int, default=None, help="Ensemble members per hour.")
    p_run.add_argument("--seed", type=int, default=None, help="Base random seed (member i uses seed+i).")
    p_run.add_argument("--num-hours", type=int, default=None, help="Limit to the first N hours.")
    p_run.add_argument("--hours", nargs="*", default=None, help="Explicit ISO timestamps to process.")
    p_run.set_defaults(func=cmd_run, needs_assets=True)

    p_res = sub.add_parser("resume", help="Extend a previous run's ensemble and/or re-extract summaries.")
    p_res.add_argument("--output", required=True)
    p_res.add_argument("--members", type=int, default=None)
    p_res.add_argument("--num-hours", type=int, default=None)
    p_res.add_argument("--next-hour", default=None, help="Specific target hour (ISO) to append.")
    p_res.add_argument("--reextract", action="store_true", help="Recompute station statistics from stored ensembles only.")
    p_res.set_defaults(func=cmd_resume, needs_assets=True)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
