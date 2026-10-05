#!/usr/bin/env python3
"""
GPUv1-F09 - source-native adapter for PhysicsNeMo AeroGraphNet on DrivAerNet v1.

This adapter orchestrates the *native* upstream AeroGraphNet training / inference
pipeline against the real DrivAerNet v1 surface meshes and CFD surface-field
labels (pressure, wall shear) to produce a drag prediction. It refuses to run
unless the required native inputs (DrivAerNet v1 mesh/fields tree plus the
upstream PhysicsNeMo AeroGraphNet source tree) and the required Python modules
(physicsnemo, dgl, pyvista, torch) are actually admitted on this host.

It never fabricates meshes, surface fields or CFD labels; when the inputs are
missing it reports the exact missing assets and exits with status 78.

Subcommands
-----------
  doctor --input <dir>          Inspect required inputs/deps; exit 78 if missing.
  run    --input <dir> --output <dir>
                               Run native AeroGraphNet training + inference.
  resume --input <dir> --output <dir>
                               Reload saved checkpoint/state and continue.

`main.py --help` never imports torch/physicsnemo/dgl/pyvista, so it is safe to
invoke without any GPU or framework present.
"""

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
import time

EXIT_OK = 0
EXIT_ERR = 1
EXIT_MISSING = 78

TASK_ID = "GPUv1-F09"

REQUIRED_FILES = [
    "upstream/physicsnemo/examples/cfd/aerographnet/train.py",
    "drivaernet/train_manifest.json",
    "drivaernet/validation_manifest.json",
    "drivaernet/geometry_and_fields",
]

REQUIRED_MODULES = ["torch", "physicsnemo", "dgl", "pyvista"]


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256(path, bufsize=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_inputs(input_dir):
    rows = []
    for rel in REQUIRED_FILES:
        p = os.path.join(input_dir, rel)
        present = os.path.exists(p)
        row = {"path": rel, "present": present, "kind": None}
        if present:
            if os.path.isdir(p):
                row["kind"] = "dir"
                entries = sorted(os.listdir(p))
                row["entry_count"] = len(entries)
                row["sample_entries"] = entries[:8]
            else:
                row["kind"] = "file"
                row["size_bytes"] = os.path.getsize(p)
                row["sha256"] = _sha256(p)
        rows.append(row)
    return rows


def probe_modules():
    rows = []
    for name in REQUIRED_MODULES:
        try:
            mod = importlib.import_module(name)
            rows.append({
                "name": name,
                "present": True,
                "version": getattr(mod, "__version__", None),
                "path": getattr(mod, "__file__", None),
            })
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": name, "present": False, "error": repr(exc)})
    return rows


def cuda_probe():
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": repr(exc)}
    ok = bool(torch.cuda.is_available())
    info = {
        "available": ok,
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
    }
    if ok:
        info["device_count"] = torch.cuda.device_count()
        info["device_name_0"] = torch.cuda.get_device_name(0)
        info["capability_0"] = list(torch.cuda.get_device_capability(0))
    return info


def _write_run_json(output_dir, report):
    os.makedirs(output_dir, exist_ok=True)
    report.setdefault("task_id", TASK_ID)
    report.setdefault("generated_at", _now())
    with open(os.path.join(output_dir, "run.json"), "w") as f:
        json.dump(report, f, indent=2)


def _emit(report, output_dir=None, exit_code=EXIT_OK):
    print(json.dumps(report, indent=2))
    if output_dir:
        _write_run_json(output_dir, report)
    return exit_code


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def cmd_doctor(args):
    input_dir = args.input
    files = probe_inputs(input_dir)
    modules = probe_modules()
    cuda = cuda_probe()
    missing_files = [r["path"] for r in files if not r["present"]]
    missing_modules = [r["name"] for r in modules if not r["present"]]
    report = {
        "task_id": TASK_ID,
        "command": "doctor",
        "input_dir": os.path.abspath(input_dir),
        "files": files,
        "modules": modules,
        "cuda": cuda,
        "missing_files": missing_files,
        "missing_modules": missing_modules,
        "status": "ok" if not (missing_files or missing_modules) else "missing",
        "generated_at": _now(),
    }
    print(json.dumps(report, indent=2))
    if missing_files or missing_modules:
        return EXIT_MISSING
    return EXIT_OK


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def cmd_run(args):
    t0 = time.time()
    input_dir = args.input
    output_dir = args.output

    if not os.path.isdir(input_dir):
        return _emit({
            "task_id": TASK_ID, "command": "run",
            "status": "BLOCKED_MISSING_INPUT_DIR",
            "input_dir": os.path.abspath(input_dir),
            "wall_s": round(time.time() - t0, 3),
        }, output_dir, EXIT_MISSING)

    # Gate 1: required native files
    files = probe_inputs(input_dir)
    missing_files = [r["path"] for r in files if not r["present"]]
    if missing_files:
        return _emit({
            "task_id": TASK_ID, "command": "run",
            "status": "BLOCKED_MISSING_INPUT_ASSETS",
            "missing_files": missing_files,
            "message": ("Native DrivAerNet v1 / PhysicsNeMo AeroGraphNet inputs are not "
                        "admitted on this host. The adapter refuses to fabricate meshes, "
                        "surface fields or CFD labels, and will not substitute a CPU path."),
            "wall_s": round(time.time() - t0, 3),
        }, output_dir, EXIT_MISSING)

    # Gate 2: required modules
    modules = probe_modules()
    missing_modules = [r["name"] for r in modules if not r["present"]]
    if missing_modules:
        return _emit({
            "task_id": TASK_ID, "command": "run",
            "status": "BLOCKED_MISSING_MODULES",
            "missing_modules": missing_modules,
            "wall_s": round(time.time() - t0, 3),
        }, output_dir, EXIT_MISSING)

    # Gate 3: real CUDA required
    cuda = cuda_probe()
    if not cuda.get("available"):
        return _emit({
            "task_id": TASK_ID, "command": "run",
            "status": "BLOCKED_NO_CUDA",
            "cuda": cuda,
            "message": "GPU task requires a real CUDA device; refusing to fall back to CPU.",
            "wall_s": round(time.time() - t0, 3),
        }, output_dir, EXIT_ERR)

    # ------------------------------------------------------------------
    # Native upstream invocation (only reached when all gates pass).
    # ------------------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)
    for sub in ("checkpoints", "predicted_fields"):
        os.makedirs(os.path.join(output_dir, sub), exist_ok=True)

    upstream_train = os.path.abspath(os.path.join(
        input_dir, "upstream/physicsnemo/examples/cfd/aerographnet/train.py"))
    upstream_root = os.path.abspath(os.path.join(
        input_dir, "upstream/physicsnemo"))

    env = dict(os.environ)
    env["PYTHONPATH"] = upstream_root + os.pathsep + env.get("PYTHONPATH", "")
    env["DRIVAERNET_TRAIN_MANIFEST"] = os.path.join(
        input_dir, "drivaernet/train_manifest.json")
    env["DRIVAERNET_VAL_MANIFEST"] = os.path.join(
        input_dir, "drivaernet/validation_manifest.json")
    env["DRIVAERNET_GEOMETRY_DIR"] = os.path.join(
        input_dir, "drivaernet/geometry_and_fields")
    env["DRIVAERNET_OUTPUT_DIR"] = os.path.abspath(output_dir)
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")

    # Source-native invocation: run the upstream train.py with the frozen
    # drivaernet/agn experiment config under Hydra.  The upstream config is
    # responsible for mesh preprocessing, message passing, loss, checkpoint
    # serialization (model + optimizer + RNG + normalization stats), and
    # for emitting .vtp fields and drag_predictions.csv under
    # $DRIVAERNET_OUTPUT_DIR.
    upstream_cmd = [
        sys.executable, upstream_train,
        "+experiment=drivaernet/agn",
        f"hydra.run.dir={os.path.abspath(output_dir)}/hydra",
        f"hydra.sweep.dir={os.path.abspath(output_dir)}/hydra",
    ]

    t_train = time.time()
    proc = subprocess.run(
        upstream_cmd,
        cwd=os.path.dirname(upstream_train),
        env=env,
        capture_output=True,
        text=True,
    )
    train_wall = round(time.time() - t_train, 3)

    ckpt_dir = os.path.join(output_dir, "checkpoints")
    ckpt_files = sorted(os.listdir(ckpt_dir)) if os.path.isdir(ckpt_dir) else []
    pred_dir = os.path.join(output_dir, "predicted_fields")
    pred_files = sorted(os.listdir(pred_dir)) if os.path.isdir(pred_dir) else []
    drag_csv = os.path.join(output_dir, "drag_predictions.csv")

    status = "TRAINING_COMPLETE" if proc.returncode == 0 else "TRAINING_FAILED"
    report = {
        "task_id": TASK_ID,
        "command": "run",
        "status": status,
        "upstream_cmd": upstream_cmd,
        "upstream_returncode": proc.returncode,
        "upstream_stdout_tail": proc.stdout[-4000:],
        "upstream_stderr_tail": proc.stderr[-4000:],
        "checkpoints": ckpt_files,
        "predicted_fields": pred_files[:32],
        "predicted_field_count": len(pred_files),
        "drag_csv_present": os.path.exists(drag_csv),
        "stages": {"upstream_train_wall_s": train_wall},
        "cuda": cuda,
        "wall_s": round(time.time() - t0, 3),
    }
    return _emit(report, output_dir, EXIT_OK if proc.returncode == 0 else EXIT_ERR)


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------

def cmd_resume(args):
    input_dir = args.input
    output_dir = args.output

    if not os.path.isdir(input_dir):
        return _emit({
            "task_id": TASK_ID, "command": "resume",
            "status": "BLOCKED_MISSING_INPUT_DIR",
            "input_dir": os.path.abspath(input_dir),
        }, output_dir, EXIT_MISSING)

    files = probe_inputs(input_dir)
    missing_files = [r["path"] for r in files if not r["present"]]
    if missing_files:
        return _emit({
            "task_id": TASK_ID, "command": "resume",
            "status": "BLOCKED_MISSING_INPUT_ASSETS",
            "missing_files": missing_files,
        }, output_dir, EXIT_MISSING)

    ckpt_dir = os.path.join(output_dir, "checkpoints")
    have_state = (os.path.isdir(ckpt_dir)
                  and any(os.scandir(ckpt_dir)))
    if not have_state:
        return _emit({
            "task_id": TASK_ID, "command": "resume",
            "status": "NO_RESUMABLE_STATE",
            "checkpoint_dir": os.path.abspath(ckpt_dir),
            "message": ("No saved checkpoint/optimizer/RNG state found. Run `run` first. "
                        "Resume is only meaningful after a real native run started."),
        }, output_dir, EXIT_MISSING)

    # Re-invoke the native upstream; the drivaernet/agn config reads the
    # existing checkpoint/optimizer state from $DRIVAERNET_OUTPUT_DIR.
    return cmd_run(args)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(f"{TASK_ID}: source-native PhysicsNeMo AeroGraphNet "
                     "DrivAerNet v1 aerodynamic surrogate adapter."),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser(
        "doctor",
        help="Inspect required inputs and modules; exit 78 if anything is missing.")
    p_doc.add_argument("--input", required=True, help="Read-only input directory")
    p_doc.set_defaults(func=cmd_doctor)

    p_run = sub.add_parser(
        "run",
        help="Run native AeroGraphNet training + inference on DrivAerNet v1.")
    p_run.add_argument("--input", required=True, help="Read-only input directory")
    p_run.add_argument("--output", required=True, help="Writable output directory")
    p_run.set_defaults(func=cmd_run)

    p_res = sub.add_parser(
        "resume",
        help="Resume from saved checkpoint/optimizer/RNG state in --output.")
    p_res.add_argument("--input", required=True, help="Read-only input directory")
    p_res.add_argument("--output", required=True, help="Writable output directory")
    p_res.set_defaults(func=cmd_resume)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
