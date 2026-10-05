#!/usr/bin/env python3
"""GPUv1-F06 — source-native adapter for the official LAMMPS Ta SNAP example
(BCC Ta, SNAP + ZBL, Kokkos CUDA) at the declared debug scale.

Subcommands
-----------
doctor --input INPUT
    Inspect the required upstream files and runtime dependencies and print a
    machine-readable report.  Exits 78 (EX_CONFIG) if anything is missing,
    0 otherwise.  Never loads a model and never executes LAMMPS dynamics.

run --input INPUT --output OUTPUT
    Copy the upstream LAMMPS tree into a bounded workspace, adapt the official
    in.snap.Ta06A script (nrep=4, 100 steps, dump/restart/thermo) and drive a
    real Kokkos-CUDA SNAP run.  Refuses to start if inputs, CUDA or the
    Kokkos/CUDA/snap/kk capability tokens are missing.

resume --input INPUT --output OUTPUT
    Continue from the saved final.restart (velocity, box and potential
    configuration preserved), 50 debug steps, and produce the incremental
    structure statistics.

Exit codes: 0 OK, 1 runtime error, 78 missing configuration.
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TASK_ID = "GPUv1-F06"
EXIT_OK = 0
EXIT_ERR = 1
EXIT_CONFIG = 78

REQUIRED_FILES = [
    "lammps/bin/lmp",
    "lammps/examples/snap/in.snap.Ta06A",
    "lammps/potentials/Ta06A.snap",
    "lammps/potentials/Ta06A.snapcoeff",
    "lammps/potentials/Ta06A.snapparam",
]

# Frozen physical parameters declared by the task specification (debug scale).
NREP = 4
STEPS_RUN = 100
STEPS_RESUME = 50
DUMP_EVERY = 10
THERMO_EVERY = 10
RDF_RMAX = 6.0
RDF_NBINS = 120

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n")


def lmp_help(binary, timeout=180):
    try:
        res = subprocess.run([str(binary), "-h"], capture_output=True,
                             text=True, timeout=timeout)
        return res.returncode, (res.stdout or "") + "\n" + (res.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return -1, f"{type(exc).__name__}: {exc}"


def require_gpu():
    """Real work requires a visible CUDA device; abort otherwise."""
    try:
        res = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                             text=True, timeout=60)
    except FileNotFoundError as exc:
        raise RuntimeError("nvidia-smi not found: no CUDA-capable GPU visible") from exc
    out = (res.stdout or "").strip()
    if res.returncode != 0 or not out:
        raise RuntimeError(
            "no visible CUDA GPU (nvidia-smi -L failed): "
            + (res.stderr or "").strip()
        )
    return out


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #


def build_doctor_report(input_dir):
    input_dir = Path(input_dir)
    rep = {
        "task_id": TASK_ID,
        "input_dir": str(input_dir),
        "required_files": REQUIRED_FILES,
        "files": {},
        "missing_files": [],
        "dependencies": {},
        "missing_dependencies": [],
        "capabilities": {},
        "missing_capabilities": [],
    }

    for rel in REQUIRED_FILES:
        path = input_dir / rel
        if path.is_file():
            rep["files"][rel] = {
                "present": True,
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        else:
            rep["files"][rel] = {"present": False, "path": str(path)}
            rep["missing_files"].append(rel)

    # --- python / system dependencies ------------------------------------- #
    try:
        import numpy  # noqa: F401  (lazy import, keeps --help light)
        rep["dependencies"]["numpy"] = getattr(numpy, "__version__", "present")
    except Exception:  # noqa: BLE001
        rep["dependencies"]["numpy"] = None
        rep["missing_dependencies"].append("numpy")

    try:
        res = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                             text=True, timeout=60)
        ok = res.returncode == 0 and bool((res.stdout or "").strip())
        rep["dependencies"]["nvidia-smi"] = (
            (res.stdout or "").strip() if ok else None
        )
        if not ok:
            rep["missing_dependencies"].append("nvidia-smi/GPU")
    except Exception:  # noqa: BLE001
        rep["dependencies"]["nvidia-smi"] = None
        rep["missing_dependencies"].append("nvidia-smi/GPU")

    # --- binary capability probing (no dynamics, only -h) ------------------ #
    binary = input_dir / "lammps/bin/lmp"
    if binary.is_file():
        rc, out = lmp_help(binary)
        rep["lmp_help_rc"] = rc
        rep["lmp_help_excerpt"] = out[:6000]
        low = out.lower()
        caps = {
            "kokkos": "kokkos" in low,
            "cuda": ("cuda" in low) or ("gpu" in low),
            "snap": "snap" in low,
            "kk": bool(re.search(r"\bkk\b", out)),
            "help_rc_zero": rc == 0,
        }
        rep["capabilities"] = caps
        for key, ok in caps.items():
            if not ok:
                rep["missing_capabilities"].append(key)
    else:
        rep["capabilities"] = {}
        rep["missing_capabilities"] = ["lmp_binary_absent"]

    rep["missing"] = (
        list(rep["missing_files"])
        + [f"dependency:{d}" for d in rep["missing_dependencies"]]
        + [f"capability:{c}" for c in rep["missing_capabilities"]]
    )
    rep["ready"] = len(rep["missing"]) == 0
    return rep


def cmd_doctor(args):
    rep = build_doctor_report(Path(args.input).resolve())
    print(json.dumps(rep, indent=2))
    if not rep["ready"]:
        print(f"[doctor] {len(rep['missing'])} missing item(s): "
              f"{', '.join(rep['missing'])}", file=sys.stderr)
        return EXIT_CONFIG
    print("[doctor] all required files, dependencies and capabilities present")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# LAMMPS input adaptation
# --------------------------------------------------------------------------- #

RUN_RE = re.compile(r"^run\b", re.I)


def transform_input(script_text, *, nrep, steps, dump_file, restart_file,
                    data_file, dump_every, thermo_every):
    """Adapt the official script in-place: fix nrep, instrument and run."""
    out, injected = [], False
    for raw in script_text.splitlines():
        s = raw.strip()
        if re.match(r"^variable\s+nrep\b", s, re.I):
            out.append(f"variable nrep equal {nrep}")
            continue
        if RUN_RE.match(s):
            if not injected:
                out.append(f"dump traj all custom {dump_every} {dump_file} "
                           "id type x y z vx vy vz")
                out.append("dump_modify traj sort id")
                out.append(f"thermo {thermo_every}")
                out.append("thermo_style custom step temp pe ke etotal press vol")
                out.append("thermo_modify flush yes")
                out.append(f"run {steps}")
                out.append(f"write_data {data_file}")
                out.append(f"write_restart {restart_file}")
                injected = True
            continue
        out.append(raw)
    if not injected:
        raise RuntimeError("upstream input has no 'run' command; cannot adapt")
    return "\n".join(out) + "\n"


PRE_READ_RE = re.compile(r"^(units|atom_style)\b", re.I)
POST_READ_RE = re.compile(
    r"^(pair_style|pair_coeff|mass|timestep|neighbor|neigh_modify)\b", re.I)
FIX_NVE_RE = re.compile(r"^fix\s+\S+\s+all\s+nve\b", re.I)


def build_resume_script(transformed_text, *, steps, dump_file, restart_in,
                        restart_out, dump_every, thermo_every):
    """Rebuild a restart-preserving continuation input (velocities + box +
    SNAP/ZBL potential configuration are retained)."""
    pre, post = [], []
    for raw in transformed_text.splitlines():
        s = raw.strip()
        if PRE_READ_RE.match(s):
            pre.append(raw)
        elif POST_READ_RE.match(s) or FIX_NVE_RE.match(s):
            post.append(raw)
    head = ["# GPUv1-F06 resume — SNAP+ZBL BCC Ta, Kokkos CUDA"] + pre + [
        f"read_restart {restart_in}"]
    tail = post + [
        f"dump traj all custom {dump_every} {dump_file} id type x y z vx vy vz",
        "dump_modify traj sort id",
        f"thermo {thermo_every}",
        "thermo_style custom step temp pe ke etotal press vol",
        "thermo_modify flush yes",
        f"run {steps}",
        f"write_restart {restart_out}",
    ]
    return "\n".join(head + tail) + "\n"


def parse_thermo(log_text):
    header, rows = None, []
    for line in log_text.splitlines():
        s = line.strip()
        if s.startswith("Step ") and "Temp" in s:
            header = s.split()
            continue
        if header and s and re.match(r"^[-+0-9.]", s):
            parts = s.split()
            if len(parts) == len(header):
                try:
                    rows.append([float(x) for x in parts])
                except ValueError:
                    continue
    return header, rows


def write_thermo_csv(path, header, rows):
    lines = [",".join(header)] if header else []
    for row in rows:
        lines.append(",".join(repr(v) for v in row))
    Path(path).write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# trajectory / RDF
# --------------------------------------------------------------------------- #


def read_dump(path):
    frames, lines = [], Path(path).read_text().splitlines()
    i, n = 0, len(lines)
    while i < n:
        if lines[i].startswith("ITEM: TIMESTEP"):
            step = int(lines[i + 1])
            natoms = int(lines[i + 3])
            box = []
            for k in range(3):
                parts = lines[i + 5 + k].split()
                box.append((float(parts[0]), float(parts[1])))
            cols = lines[i + 9].split()[2:]
            atoms = [lines[i + 10 + a].split() for a in range(natoms)]
            frames.append({"step": step, "box": box, "cols": cols,
                           "atoms": atoms})
            i += 10 + natoms
        else:
            i += 1
    return frames


def _coords(frame):
    import numpy as np
    idx = {c: k for k, c in enumerate(frame["cols"])}
    return np.array([[float(r[idx[c]]) for c in ("x", "y", "z")]
                     for r in frame["atoms"]], dtype=float)


def compute_rdf(frame, rmax=RDF_RMAX, nbins=RDF_NBINS):
    import numpy as np
    pos = _coords(frame)
    box = frame["box"]
    lengths = np.array([box[k][1] - box[k][0] for k in range(3)])
    natoms = len(pos)
    volume = float(np.prod(lengths))

    diff = pos[:, None, :] - pos[None, :, :]
    diff -= lengths * np.round(diff / lengths)
    dist = np.sqrt((diff ** 2).sum(-1))
    iu = np.triu_indices(natoms, k=1)
    pairs = dist[iu]

    hist, edges = np.histogram(pairs, bins=nbins, range=(0.0, rmax))
    shell = (4.0 / 3.0) * math.pi * (edges[1:] ** 3 - edges[:-1] ** 3)
    rho = natoms / volume
    gr = hist / (rho * natoms * shell)
    centers = 0.5 * (edges[1:] + edges[:-1])
    return centers, gr, pairs, natoms, volume, lengths


def structure_stats(centers, gr, pairs, natoms, volume, lengths,
                    first_frame, last_frame):
    import numpy as np
    peak = int(np.argmax(gr))
    r_peak = float(centers[peak])
    # coordination number up to the first minimum after the first peak
    lo = peak
    hi = peak
    for k in range(peak, len(gr) - 1):
        if gr[k + 1] > gr[k]:
            hi = k
            break
    else:
        hi = len(gr) - 1
    dr = float(centers[1] - centers[0])
    rho = natoms / volume
    coord = float(np.sum(gr[lo:hi + 1] * rho * 4.0 * math.pi
                         * centers[lo:hi + 1] ** 2 * dr))

    # minimum-image MSD between first and last saved frame
    a = _coords(first_frame)
    b = _coords(last_frame)
    ll = np.array([last_frame["box"][k][1] - last_frame["box"][k][0]
                   for k in range(3)])
    d = b - a
    d -= ll * np.round(d / ll)
    msd = float((d ** 2).sum(-1).mean())

    return {
        "n_atoms": int(natoms),
        "box_lengths_angstrom": [float(x) for x in lengths],
        "volume_angstrom3": float(volume),
        "density_atoms_per_angstrom3": float(rho),
        "rdf_first_peak_r_angstrom": r_peak,
        "rdf_first_peak_g": float(gr[peak]),
        "coordination_number_first_shell": coord,
        "msd_between_first_and_last_frame_angstrom2": msd,
        "pair_count": int(len(pairs)),
        "mean_pair_distance_angstrom": float(np.mean(pairs)),
    }


def write_rdf_csv(path, centers, gr):
    lines = ["r_angstrom,g_r"]
    lines += [f"{r:.6f},{g:.6f}" for r, g in zip(centers, gr)]
    Path(path).write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# run / resume
# --------------------------------------------------------------------------- #

GPU_MARKERS = ("kokkos::cuda", "kokkos", "cuda", "device", "gpu",
               "executing on")


def gpu_proof(text):
    low = text.lower()
    return {
        "kokkos_mentioned": "kokkos" in low,
        "cuda_mentioned": ("cuda" in low) or ("gpu" in low),
        "has_explicit_backend_line": bool(
            re.search(r"kokkos::(cuda|serial|openmp|threads)", low)),
    }


def prepare_workspace(input_dir, ws):
    src = Path(input_dir) / "lammps"
    if ws.exists():
        shutil.rmtree(ws)
    (ws / "lammps/bin").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "bin/lmp", ws / "lammps/bin/lmp")
    os.chmod(ws / "lammps/bin/lmp", 0o755)
    shutil.copytree(src / "examples/snap", ws / "lammps/examples/snap",
                    dirs_exist_ok=True)
    shutil.copytree(src / "potentials", ws / "lammps/potentials",
                    dirs_exist_ok=True)
    return ws / "lammps"


def run_lammps(lmp, cwd, in_name, log_path, stdout_path, timeout):
    cmd = [str(lmp), "-k", "on", "g", "1", "-sf", "kk", "-pk", "kokkos",
           "-in", in_name, "-log", str(log_path)]
    env = dict(os.environ)
    env.setdefault("OMP_NUM_THREADS", "1")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                         timeout=timeout, env=env)
    wall = time.time() - t0
    Path(stdout_path).write_text((res.stdout or "") + "\n----STDERR----\n"
                                 + (res.stderr or ""))
    return cmd, res.returncode, wall, (res.stdout or ""), (res.stderr or "")


def load_log_text(log_path, stdout_path):
    parts = []
    for p in (log_path, stdout_path):
        p = Path(p)
        if p.is_file():
            parts.append(p.read_text(errors="replace"))
    return "\n".join(parts)


def blocked_run_json(output_dir, doc, wall):
    write_json(output_dir / "run.json", {
        "task_id": TASK_ID,
        "status": "blocked_missing_inputs",
        "mode": "run",
        "missing": doc["missing"],
        "message": ("Required upstream assets/dependencies/capabilities are "
                    "not mounted. No substitute (L-J, analytic, CPU lmp or "
                    "fabricated data) was used and no acceptance is claimed."),
        "wall_s": wall,
    })


def cmd_run(args):
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    t_all = time.time()

    doc = build_doctor_report(input_dir)
    write_json(output_dir / "doctor_report.json", doc)
    if not doc["ready"]:
        blocked_run_json(output_dir, doc, time.time() - t_all)
        print(json.dumps(doc, indent=2))
        print(f"[run] refusing to start: {len(doc['missing'])} missing item(s): "
              f"{', '.join(doc['missing'])}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        gpu_list = require_gpu()
    except RuntimeError as exc:
        write_json(output_dir / "run.json", {
            "task_id": TASK_ID, "status": "failed_no_cuda",
            "message": str(exc), "wall_s": time.time() - t_all})
        print(f"[run] {exc}", file=sys.stderr)
        return EXIT_ERR

    stage = output_dir / "stage1"
    stage.mkdir(parents=True, exist_ok=True)
    ws = prepare_workspace(input_dir, output_dir / "workspace")
    run_dir = ws / "examples/snap"
    lmp = ws / "bin/lmp"

    src_script = (input_dir / "lammps/examples/snap/in.snap.Ta06A").read_text()
    adapted = transform_input(
        src_script, nrep=NREP, steps=STEPS_RUN,
        dump_file=str(stage / "trajectory.dump"),
        restart_file=str(stage / "final.restart"),
        data_file=str(stage / "initial.data"),
        dump_every=DUMP_EVERY, thermo_every=THERMO_EVERY)
    in_path = run_dir / "in.gpuv1_f06.lmp"
    in_path.write_text(adapted)

    cmd, rc, wall, _out, err = run_lammps(
        lmp, run_dir, in_path.name,
        stage / "log.lammps", stage / "stdout.log", args.timeout)

    log_text = load_log_text(stage / "log.lammps", stage / "stdout.log")
    proof = gpu_proof(log_text)
    if rc != 0:
        write_json(output_dir / "run.json", {
            "task_id": TASK_ID, "status": "lammps_failed", "returncode": rc,
            "command": cmd, "stderr_tail": err[-4000:],
            "wall_s": time.time() - t_all})
        print(f"[run] LAMMPS exited {rc}", file=sys.stderr)
        return EXIT_ERR
    if not (proof["kokkos_mentioned"] and proof["cuda_mentioned"]):
        write_json(output_dir / "run.json", {
            "task_id": TASK_ID, "status": "gpu_backend_unproven",
            "gpu_proof": proof, "command": cmd,
            "wall_s": time.time() - t_all})
        print("[run] execution log does not prove a Kokkos CUDA backend",
              file=sys.stderr)
        return EXIT_ERR

    header, thermo_rows = parse_thermo(log_text)
    write_thermo_csv(output_dir / "thermo.csv", header, thermo_rows)

    frames = read_dump(stage / "trajectory.dump")
    if len(frames) < 2:
        print("[run] trajectory has too few frames", file=sys.stderr)
        return EXIT_ERR
    centers, gr, pairs, natoms, volume, lengths = compute_rdf(frames[-1])
    write_rdf_csv(output_dir / "rdf.csv", centers, gr)
    stats = structure_stats(centers, gr, pairs, natoms, volume, lengths,
                            frames[0], frames[-1])
    stats["stage"] = "stage1"
    stats["frames_saved"] = len(frames)
    stats["frame_steps"] = [f["step"] for f in frames]
    write_json(output_dir / "structure_stats.json", stats)

    # top-level deliverables
    shutil.copy2(stage / "initial.data", output_dir / "initial.data")
    shutil.copy2(stage / "final.restart", output_dir / "final.restart")
    shutil.copy2(stage / "trajectory.dump", output_dir / "trajectory.dump")

    velocity_lines = [ln.strip() for ln in src_script.splitlines()
                      if ln.strip().lower().startswith("velocity")]
    artifacts = {}
    for name in ("initial.data", "final.restart", "trajectory.dump",
                 "thermo.csv", "rdf.csv", "structure_stats.json"):
        p = output_dir / name
        artifacts[name] = {"sha256": sha256_file(p), "size": p.stat().st_size}

    write_json(output_dir / "run.json", {
        "task_id": TASK_ID,
        "status": "completed",
        "mode": "run",
        "scale": "debug",
        "reference_large_executed": False,
        "backend": "LAMMPS native Ta SNAP Kokkos CUDA",
        "command": cmd,
        "workspace": str(output_dir / "workspace"),
        "device": gpu_list,
        "gpu_proof": proof,
        "upstream": {r: doc["files"][r]["sha256"] for r in REQUIRED_FILES},
        "adapted_input_sha256": sha256_text(adapted),
        "parameters": {
            "nrep": NREP, "steps": STEPS_RUN, "dump_every": DUMP_EVERY,
            "thermo_every": THERMO_EVERY, "pair_style": "snap + zbl (official)",
            "ensemble": "NVE", "suffix": "kk", "kokkos_gpu": 1,
            "velocity_commands": velocity_lines,
            "rdf_rmax": RDF_RMAX, "rdf_nbins": RDF_NBINS,
        },
        "timings": {"lammps_wall_s": wall, "total_wall_s": time.time() - t_all},
        "artifacts": artifacts,
        "structure_stats": stats,
        "continuation": {
            "restart": str(output_dir / "final.restart"),
            "command": "python solution/main.py resume --input input --output output",
            "target_5ps_steps": 10000,
        },
    })
    print(f"[run] completed in {wall:.2f}s; artifacts in {output_dir}")
    return EXIT_OK


def cmd_resume(args):
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    t_all = time.time()

    doc = build_doctor_report(input_dir)
    if not doc["ready"]:
        write_json(output_dir / "run_resume.json", {
            "task_id": TASK_ID, "status": "blocked_missing_inputs",
            "mode": "resume", "missing": doc["missing"],
            "wall_s": time.time() - t_all})
        print(f"[resume] missing inputs: {', '.join(doc['missing'])}",
              file=sys.stderr)
        return EXIT_CONFIG

    restart = output_dir / "final.restart"
    if not restart.is_file():
        write_json(output_dir / "run_resume.json", {
            "task_id": TASK_ID, "status": "no_state",
            "message": f"{restart} not found; run 'run' first",
            "wall_s": time.time() - t_all})
        print(f"[resume] no saved state at {restart}", file=sys.stderr)
        return EXIT_ERR

    try:
        gpu_list = require_gpu()
    except RuntimeError as exc:
        write_json(output_dir / "run_resume.json", {
            "task_id": TASK_ID, "status": "failed_no_cuda",
            "message": str(exc), "wall_s": time.time() - t_all})
        print(f"[resume] {exc}", file=sys.stderr)
        return EXIT_ERR

    stage2 = output_dir / "stage2"
    stage2.mkdir(parents=True, exist_ok=True)
    ws = prepare_workspace(input_dir, output_dir / "workspace")
    run_dir = ws / "examples/snap"
    lmp = ws / "bin/lmp"

    # stage1 state must be inside the fresh workspace run dir
    w_restart = run_dir / "stage1_final.restart"
    shutil.copy2(restart, w_restart)

    src_script = (input_dir / "lammps/examples/snap/in.snap.Ta06A").read_text()
    transformed = transform_input(
        src_script, nrep=NREP, steps=STEPS_RUN,
        dump_file=str(stage2 / "trajectory_stage1.dump"),
        restart_file=str(stage2 / "stage1.restart"),
        data_file=str(stage2 / "stage1.data"),
        dump_every=DUMP_EVERY, thermo_every=THERMO_EVERY)
    resume_script = build_resume_script(
        transformed, steps=STEPS_RESUME,
        dump_file=str(stage2 / "trajectory_resume.dump"),
        restart_in=str(w_restart),
        restart_out=str(stage2 / "final.restart"),
        dump_every=DUMP_EVERY, thermo_every=THERMO_EVERY)
    in_path = run_dir / "in.gpuv1_f06_resume.lmp"
    in_path.write_text(resume_script)

    cmd, rc, wall, _out, err = run_lammps(
        lmp, run_dir, in_path.name,
        stage2 / "log.lammps", stage2 / "stdout.log", args.timeout)

    log_text = load_log_text(stage2 / "log.lammps", stage2 / "stdout.log")
    proof = gpu_proof(log_text)
    if rc != 0 or not (proof["kokkos_mentioned"] and proof["cuda_mentioned"]):
        write_json(output_dir / "run_resume.json", {
            "task_id": TASK_ID, "status": "resume_failed",
            "returncode": rc, "gpu_proof": proof, "command": cmd,
            "stderr_tail": err[-4000:], "wall_s": time.time() - t_all})
        print("[resume] LAMMPS run failed or GPU backend unproven",
              file=sys.stderr)
        return EXIT_ERR

    header, thermo_rows = parse_thermo(log_text)
    write_thermo_csv(output_dir / "thermo_resume.csv", header, thermo_rows)

    base_frames = read_dump(output_dir / "trajectory.dump")
    new_frames = read_dump(stage2 / "trajectory_resume.dump")
    if not new_frames:
        print("[resume] empty resume trajectory", file=sys.stderr)
        return EXIT_ERR
    centers, gr, pairs, natoms, volume, lengths = compute_rdf(new_frames[-1])
    write_rdf_csv(output_dir / "rdf_resume.csv", centers, gr)
    stats = structure_stats(centers, gr, pairs, natoms, volume, lengths,
                            base_frames[-1], new_frames[-1])
    stats["stage"] = "stage2_resume"
    stats["resume_steps"] = STEPS_RESUME
    stats["frames_saved"] = len(new_frames)
    write_json(output_dir / "structure_stats_resume.json", stats)

    shutil.copy2(stage2 / "final.restart", output_dir / "final_resume.restart")
    shutil.copy2(stage2 / "trajectory_resume.dump",
                 output_dir / "trajectory_resume.dump")

    artifacts = {}
    for name in ("final_resume.restart", "trajectory_resume.dump",
                 "thermo_resume.csv", "rdf_resume.csv",
                 "structure_stats_resume.json"):
        p = output_dir / name
        artifacts[name] = {"sha256": sha256_file(p), "size": p.stat().st_size}

    write_json(output_dir / "run_resume.json", {
        "task_id": TASK_ID,
        "status": "completed",
        "mode": "resume",
        "command": cmd,
        "device": gpu_list,
        "gpu_proof": proof,
        "restart_sha256_in": sha256_file(restart),
        "parameters": {
            "steps": STEPS_RESUME, "dump_every": DUMP_EVERY,
            "thermo_every": THERMO_EVERY, "ensemble": "NVE",
            "suffix": "kk", "kokkos_gpu": 1,
            "preserved": ["velocities", "box", "snap+zbl potential",
                          "timestep", "neighbor settings"],
        },
        "timings": {"lammps_wall_s": wall, "total_wall_s": time.time() - t_all},
        "artifacts": artifacts,
        "structure_stats": stats,
        "note": ("Debug continuation is 50 steps. The 5 ps (10000 step) "
                 "continuation of the reference-large instance is NOT "
                 "executed here."),
    })
    print(f"[resume] completed in {wall:.2f}s")
    return EXIT_OK


# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-F06 — LAMMPS Ta SNAP Kokkos CUDA source-native adapter")
    sub = ap.add_subparsers(dest="cmd")

    p_doc = sub.add_parser("doctor",
                           help="inspect required inputs and dependencies")
    p_doc.add_argument("--input", required=True)

    p_run = sub.add_parser("run", help="stage-1 native SNAP Kokkos CUDA run")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--timeout", type=int, default=3600)

    p_res = sub.add_parser("resume",
                           help="continue from final.restart (requires state)")
    p_res.add_argument("--input", required=True)
    p_res.add_argument("--output", required=True)
    p_res.add_argument("--timeout", type=int, default=3600)

    args = ap.parse_args()
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "resume":
        return cmd_resume(args)
    ap.print_help()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
