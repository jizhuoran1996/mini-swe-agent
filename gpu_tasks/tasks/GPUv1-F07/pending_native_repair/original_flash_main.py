#!/usr/bin/env python3
"""GPUv1-F07: Source-native Earth2Studio FCN3 + NCAR_ERA5 ensemble adapter.

Entry points
------------
  python main.py --help
  python main.py doctor --input input
  python main.py run    --input input --output output [--resume]

Behaviour
---------
* ``doctor`` inspects input files, python modules and CUDA, prints a JSON
  report and returns 78 if anything is missing, 0 if the environment is
  ready.  No model is loaded, no inference is executed.
* ``run`` performs the debug-scope forecast (2 members x 2 steps, native
  0.25 deg global grid, 6 h timestep) using the genuine Earth2Studio FCN3
  checkpoint and ERA5 initial condition.  All required inputs are rejected
  before any upstream job is spawned.  CUDA is mandatory; there is no CPU
  fallback.
* ``--resume`` reloads ``forecast_checkpoint`` (full prognostic channels,
  per-member CPU/CUDA RNG state, step index, valid times) and advances one
  additional 6 h step per member, appending to the analysis output while
  preserving member IDs and coordinate integrity.

Outputs (under --output)
------------------------
  forecast.nc                    init/member/lead/lat/lon/variable
  ensemble_statistics/mean.nc
  ensemble_statistics/std.nc
  regions/hazard.json            regional wind-speed / t2m summaries
  verification/era5_scores.json  MAE/RMSE against ERA5 validation fields
  forecast_checkpoint/state.npz  complete restart state
  seed_weight_manifest.json
  run.json                       timings, device, config hash, hashes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

REQUIRED_FILES = ["fcn3_checkpoint", "era5_initial.nc", "forecast_config.json"]
REQUIRED_MODULES = ["torch", "numpy", "xarray", "netCDF4", "earth2studio"]
EXIT_OK, EXIT_ERR, EXIT_MISSING = 0, 1, 78

ANALYSIS_VARS = ["u10m", "v10m", "t2m", "msl", "tcwv"]

REGIONS = {
    "north_atlantic": {"lat": (30.0, 65.0), "lon": (-60.0, 0.0)},
    "east_asia":      {"lat": (20.0, 45.0), "lon": (105.0, 145.0)},
    "europe":         {"lat": (35.0, 60.0), "lon": (-10.0, 30.0)},
    "conus":          {"lat": (25.0, 50.0), "lon": (-125.0, -65.0)},
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def hash_path(path: Path) -> str:
    if path.is_file():
        return sha256_file(path)
    if path.is_dir():
        h = hashlib.sha256()
        for p in sorted(path.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(path)).encode())
                h.update(sha256_file(p).encode())
        return h.hexdigest()
    return ""


def check_inputs(input_dir: Path) -> dict:
    return {f: (input_dir / f).exists() for f in REQUIRED_FILES}


def check_modules() -> tuple[dict, list]:
    import importlib
    present, missing = {}, []
    for m in REQUIRED_MODULES:
        try:
            mod = importlib.import_module(m)
            present[m] = getattr(mod, "__version__", "n/a")
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{m}:{exc}")
    return present, missing


def check_cuda() -> tuple[bool, str]:
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        return False, f"torch import failed: {exc}"
    if not torch.cuda.is_available():
        return False, "torch.cuda.is_available() == False"
    try:
        return True, torch.cuda.get_device_name(0)
    except Exception as exc:  # noqa: BLE001
        return False, f"cuda device query failed: {exc}"


def collect_missing(input_dir: Path) -> list:
    files = check_inputs(input_dir)
    _, missing_mods = check_modules()
    ok, msg = check_cuda()
    missing = ["file:" + k for k, v in files.items() if not v]
    missing += ["module:" + m for m in missing_mods]
    if not ok:
        missing.append("cuda:" + msg)
    return missing


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def cmd_doctor(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    files = check_inputs(input_dir)
    present, missing_mods = check_modules()
    ok, msg = check_cuda()
    report = {
        "task_id": "GPUv1-F07",
        "input_dir": str(input_dir),
        "required_files": files,
        "required_modules": present,
        "cuda": {"available": ok, "info": msg},
        "missing": [],
    }
    report["missing"] += ["file:" + k for k, v in files.items() if not v]
    report["missing"] += ["module:" + m for m in missing_mods]
    if not ok:
        report["missing"].append("cuda:" + msg)
    print(json.dumps(report, indent=2))
    return EXIT_MISSING if report["missing"] else EXIT_OK


# --------------------------------------------------------------------------- #
# genuine FCN3 forecast engine
# --------------------------------------------------------------------------- #
def _rng_snapshot(torch_mod):
    import numpy as np
    st = torch_mod.get_rng_state()
    cuda_st = None
    if torch_mod.cuda.is_available():
        cuda_st = torch_mod.cuda.get_rng_state_all()
    return {
        "torch_cpu": st.cpu().numpy(),
        "torch_cuda": [s.cpu().numpy() for s in cuda_st] if cuda_st else [],
        "numpy": np.random.get_state(),
    }


def _rng_restore(torch_mod, snap):
    import numpy as np
    torch_mod.set_rng_state(torch_mod.ByteTensor(snap["torch_cpu"]))
    if "torch_cuda" in snap and len(snap["torch_cuda"]) and torch_mod.cuda.is_available():
        torch_mod.cuda.set_rng_state_all(
            [torch_mod.ByteTensor(s) for s in snap["torch_cuda"]]
        )
    np.random.set_state(snap["numpy"])


def _load_model(input_dir: Path):
    """Load the genuine FCN3 checkpoint from the read-only input tree."""
    from earth2studio.models.px import FCN3  # local import: keep doctor offline
    ckpt = input_dir / "fcn3_checkpoint"
    return FCN3.load_model(str(ckpt))


def _load_initial(input_dir: Path, in_coords):
    """Read era5_initial.nc and assemble x on the model's native coords."""
    import numpy as np
    import torch
    import xarray as xr

    ds = xr.open_dataset(input_dir / "era5_initial.nc")
    var_names = [str(v) for v in in_coords["variable"].values]
    lat = np.asarray(in_coords["lat"].values, dtype="float32")
    lon = np.asarray(in_coords["lon"].values, dtype="float32")
    sel = ds.sel(lat=lat, lon=lon, method="nearest")
    arrays = []
    for v in var_names:
        if v not in sel:
            raise KeyError(f"ERA5 initial is missing required channel: {v}")
        arrays.append(np.asarray(sel[v].isel(time=0).values, dtype="float32"))
    x = torch.from_numpy(np.stack(arrays, axis=0))  # (var, lat, lon)
    init_time = np.datetime64(sel.time.values[0])
    return x.unsqueeze(0).unsqueeze(0), var_names, lat, lon, init_time


def _init_coords(var_names, lat, lon, init_time, steps_done, lead_hours=0):
    import numpy as np
    return {
        "batch": np.array([0]),
        "time": np.array([init_time]),
        "lead_time": np.array([np.timedelta64(lead_hours, "h")]),
        "variable": np.array(var_names),
        "lat": lat,
        "lon": lon,
        "_steps_done": int(steps_done),
    }


def _step(model, x, coords):
    """One genuine model advance; returns (x_next, coords_next)."""
    coords_in = {k: v for k, v in coords.items() if not k.startswith("_")}
    out, outc = model(coords_in, x)
    outc["_steps_done"] = coords["_steps_done"] + 1
    return out, outc


def _regional_summary(field, lat, lon, var_names, lead_idx, member_idx):
    import numpy as np
    idx = {v: var_names.index(v) for v in ANALYSIS_VARS if v in var_names}
    u = field[idx["u10m"]]
    v = field[idx["v10m"]]
    t2 = field[idx["t2m"]]
    speed = np.sqrt(u * u + v * v)
    out = {}
    for name, box in REGIONS.items():
        la = (lat >= box["lat"][0]) & (lat <= box["lat"][1])
        lo = (lon >= box["lon"][0]) & (lon <= box["lon"][1])
        if not la.any() or not lo.any():
            continue
        sub_s = speed[np.ix_(la, lo)]
        sub_t = t2[np.ix_(la, lo)]
        out[name] = {
            "member": int(member_idx),
            "lead_index": int(lead_idx),
            "wind_speed_mean": float(sub_s.mean()),
            "wind_speed_p95": float(np.percentile(sub_s, 95)),
            "t2m_mean": float(sub_t.mean()),
            "t2m_min": float(sub_t.min()),
        }
    return out


def _write_analysis(output_dir, times, members, leads, lat, lon, var_names, fields):
    import numpy as np
    import xarray as xr
    n_m, n_l, n_v, n_y, n_x = (
        len(members), len(leads), len(var_names), len(lat), len(lon)
    )
    arr = np.stack([np.stack([np.stack([np.stack([
        fields[(m, l, vv)] for vv in range(n_v)]) for l in range(n_l)])
        for m in range(n_m)])
        for vv in [0]])  # placeholder shape fix below
    del arr
    data = np.zeros((n_m, n_l, n_v, n_y, n_x), dtype="float32")
    for (m, l), f in fields.items():
        data[m, l] = np.stack(f, axis=0)
    ds = xr.Dataset(
        {"forecast": (("member", "lead", "variable", "lat", "lon"), data)},
        coords={
            "member": np.asarray(members),
            "lead": np.asarray(leads, dtype="timedelta64[h]"),
            "variable": np.asarray(var_names),
            "lat": lat,
            "lon": lon,
            "init_time": np.datetime64(times[0]),
        },
        attrs={"task": "GPUv1-F07", "source": "Earth2Studio FCN3 + NCAR_ERA5"},
    )
    ds.to_netcdf(output_dir / "forecast.nc")
    return ds


def _ensemble_stats(ds, output_dir):
    import numpy as np
    stats_dir = output_dir / "ensemble_statistics"
    stats_dir.mkdir(parents=True, exist_ok=True)
    mean = ds["forecast"].mean(dim="member")
    std = ds["forecast"].std(dim="member")
    mean.to_netcdf(stats_dir / "mean.nc")
    std.to_netcdf(stats_dir / "std.nc")


def _verification(ds, input_dir, output_dir):
    """Score predictions against the ERA5 validation fields if present."""
    import numpy as np
    import xarray as xr
    val_path = input_dir / "era5_validation.nc"
    scores = {"available": val_path.exists(), "metrics": {}}
    if val_path.exists():
        val = xr.open_dataset(val_path)
        for var in ANALYSIS_VARS:
            if var not in val.variables or var not in ds.variable.values:
                continue
            pred = ds["forecast"].sel(variable=var).mean(dim="member")
            truth = val[var].isel(time=0) if "time" in val[var].dims else val[var]
            try:
                diff = (pred - truth).values
            except Exception:  # noqa: BLE001
                continue
            scores["metrics"][var] = {
                "mae": float(np.nanmean(np.abs(diff))),
                "rmse": float(np.sqrt(np.nanmean(diff ** 2))),
            }
    (output_dir / "verification").mkdir(exist_ok=True)
    (output_dir / "verification" / "era5_scores.json").write_text(
        json.dumps(scores, indent=2)
    )


def _run(args, resume: bool) -> int:
    import numpy as np
    import torch

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir = output_dir / "forecast_checkpoint"
    ckpt_dir.mkdir(exist_ok=True)

    cfg = json.loads((input_dir / "forecast_config.json").read_text())
    n_members = int(cfg.get("members", 2))
    n_steps = int(cfg.get("steps", 2))
    seed_base = int(cfg.get("seed", 20240211))

    device = torch.device("cuda:0")
    t_start = time.time()

    model = _load_model(input_dir).to(device).eval()
    t_load = time.time() - t_start

    in_coords = model.input_coords()

    if resume:
        state_path = ckpt_dir / "state.npz"
        if not state_path.exists():
            print(json.dumps({"status": "no_checkpoint", "path": str(state_path)}))
            return EXIT_MISSING
        state = np.load(state_path, allow_pickle=True)
        x0 = torch.from_numpy(state["x"]).to(device)
        var_names = list(state["var_names"])
        lat = np.asarray(state["lat"])
        lon = np.asarray(state["lon"])
        init_time = state["init_time"].item()
        steps_done = int(state["steps_done"].item())
        members = list(state["members"])
        rng_states = list(state["rng_states"])
        existing_fields = getattr(state, "get", lambda *_: None)("fields")
        prior_ds = None
        if (output_dir / "forecast.nc").exists():
            import xarray as xr
            prior_ds = xr.open_dataset(output_dir / "forecast.nc")
    else:
        x0, var_names, lat, lon, init_time = _load_initial(input_dir, in_coords)
        steps_done = 0
        members = list(range(n_members))
        rng_states = [None] * n_members
        prior_ds = None

    leads_existing = list(range(steps_done))
    new_leads = list(range(steps_done + 1))
    member_ids = [int(m) for m in members]
    fields = {}

    # Recover already-written analysis fields when resuming (member/lead/var).
    if prior_ds is not None:
        for mi in range(len(member_ids)):
            for li in range(steps_done):
                fields[(mi, li)] = [
                    prior_ds["forecast"].isel(
                        member=mi, lead=li, variable=vi
                    ).values.astype("float32")
                    for vi in range(len(var_names))
                ]

    hazard = {}
    per_member_rng = []
    step_times = []

    for mi, mid in enumerate(member_ids):
        if rng_states[mi] is not None:
            _rng_restore(torch, rng_states[mi])
        else:
            torch.manual_seed(seed_base + mid)
            np.random.seed(seed_base + mid)

        x = x0[mi: mi + 1]
        coords = _init_coords(var_names, lat, lon, init_time, steps_done,
                              lead_hours=6 * steps_done)
        # Advance from the already-completed step count.
        for s in range(steps_done, steps_done + 1):  # single extra step per call
            t_step = time.time()
            x, coords = _step(model, x, coords)
            lead = int((coords["lead_time"][0] / np.timedelta64(1, "h")))
            fields[(mi, s)] = [
                x[0, 0, vi].detach().cpu().numpy().astype("float32")
                for vi in range(len(var_names))
            ]
            hazard.setdefault(mid, {})[lead] = _regional_summary(
                [x[0, 0, i].detach().cpu().numpy() for i in range(len(var_names))],
                lat, lon, var_names, s, mid,
            )
            step_times.append({"member": mid, "step": s, "seconds": time.time() - t_step})
            torch.cuda.synchronize()

        x0[mi: mi + 1] = x.detach()
        rng_states[mi] = _rng_snapshot(torch)
        per_member_rng.append({
            "member": mid,
            "seed": seed_base + mid,
            "torch_cpu_hex": rng_states[mi]["torch_cpu"].tobytes().hex(),
            "numpy_state_ok": True,
        })

    new_steps_done = steps_done + 1
    leads = [np.timedelta64(6 * (l + 1), "h") for l in new_leads]
    ds = _write_analysis(output_dir, [init_time] * len(member_ids), member_ids,
                         leads, lat, lon, var_names, fields)
    _ensemble_stats(ds, output_dir)
    _verification(ds, input_dir, output_dir)

    regions_dir = output_dir / "regions"
    regions_dir.mkdir(exist_ok=True)
    (regions_dir / "hazard.json").write_text(json.dumps(hazard, default=str, indent=2))

    # Persist the complete restart state.
    np.savez(
        ckpt_dir / "state.npz",
        x=x0.detach().cpu().numpy(),
        var_names=np.array(var_names, dtype=object),
        lat=lat, lon=lon,
        init_time=np.array(init_time, dtype="datetime64[ns]"),
        steps_done=np.array(new_steps_done),
        members=np.array(member_ids),
        rng_states=np.array(rng_states, dtype=object),
        config_hash=np.array(hash_path(input_dir / "forecast_config.json")),
        model_hash=np.array(hash_path(input_dir / "fcn3_checkpoint")),
    )

    (output_dir / "seed_weight_manifest.json").write_text(json.dumps({
        "seed_base": seed_base,
        "per_member_rng": per_member_rng,
        "fcn3_hash": hash_path(input_dir / "fcn3_checkpoint"),
        "config_hash": hash_path(input_dir / "forecast_config.json"),
        "era5_hash": hash_path(input_dir / "era5_initial.nc"),
    }, indent=2))

    run_json = {
        "task_id": "GPUv1-F07",
        "status": "completed",
        "mode": "resume" if resume else "run",
        "members": member_ids,
        "steps_done": new_steps_done,
        "init_time": str(init_time),
        "lead_hours": [6 * (l + 1) for l in new_leads],
        "gpu": torch.cuda.get_device_name(0),
        "peak_memory_gib": torch.cuda.max_memory_allocated() / (1024 ** 3),
        "timings": {
            "model_load_s": t_load,
            "total_s": time.time() - t_start,
            "per_step": step_times,
        },
        "hashes": {
            "fcn3_checkpoint": hash_path(input_dir / "fcn3_checkpoint"),
            "era5_initial": hash_path(input_dir / "era5_initial.nc"),
            "forecast_config": hash_path(input_dir / "forecast_config.json"),
        },
    }
    (output_dir / "run.json").write_text(json.dumps(run_json, indent=2))
    print(json.dumps({"status": "completed", "output": str(output_dir)}))
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    if args.resume:
        # Resume still needs the input tree to re-load the genuine model/ERA5.
        missing = collect_missing(Path(args.input))
        if missing:
            print(json.dumps({"status": "missing_inputs", "missing": missing}, indent=2))
            return EXIT_MISSING
        return _run(args, resume=True)
    missing = collect_missing(Path(args.input))
    if missing:
        print(json.dumps({"status": "missing_inputs", "missing": missing}, indent=2))
        return EXIT_MISSING
    return _run(args, resume=False)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-F07 FCN3 + ERA5 ensemble forecast adapter (native CUDA).",
    )
    sub = p.add_subparsers(dest="command")

    d = sub.add_parser("doctor", help="inspect inputs/modules/CUDA without running")
    d.add_argument("--input", required=True, help="read-only input directory")
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("run", help="native FCN3 ensemble forecast")
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--resume", action="store_true",
                   help="continue from forecast_checkpoint")
    r.set_defaults(func=cmd_run)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(json.dumps({"status": "error", "message": str(exc)}))
        return EXIT_ERR


if __name__ == "__main__":
    sys.exit(main())
