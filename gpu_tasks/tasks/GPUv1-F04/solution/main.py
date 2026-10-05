#!/usr/bin/env python3
"""
GPUv1-F04 - Complete catalytic adsorption initial-state relaxation and energy ranking.

Source-native adapter for the OC20 IS2RE validation initial structures relaxed with the
official EquiformerV2 153M All+MD checkpoint along the upstream `main_oc20.py`
relaxation path (atomicarchitects/equiformer_v2 @ d5ad4be729b56f74012ebb7f097f77c5b00a1004).

That upstream tree imports `ocpmodels.common` and registers `nets` / `oc20.trainer`.
The calculator is therefore the original
    ocpmodels.common.relaxation.ase_utils.OCPCalculator
bound to the provided `equiformer_v2_153M_all_md.pt`. No newer UMA / pretrained-MLIP
calculator is used.

Subcommands
    doctor  -- inspect the read-only input tree and runtime dependencies.
               Lists every missing item and exits 78 if anything is unavailable.
    run     -- execute the declared debug workload: per validation partition take the
               two sids with the smallest SHA256(sid), relax them on GPU with the fixed
               optimiser / force threshold / max-step recipe, save structures, energies,
               trajectory summaries, optimizer state and run.json.
    resume  -- continue the saved NON-converged systems up to the declared total step
               budget without re-initialising positions.

Only solution/ and output/ are written. The input tree is opened read-only.  No network,
no downloads, no fabricated inputs, no CPU fallback for the numerical work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
import time
import traceback
from pathlib import Path

TASK_ID = "GPUv1-F04"
BACKEND = "OC20 EquiformerV2 153M All+MD relaxation"
UPSTREAM_COMMIT = "atomicarchitects/equiformer_v2@d5ad4be729b56f74012ebb7f097f77c5b00a1004"
PARTITIONS = ("val_id", "val_ood_ads", "val_ood_cat", "val_ood_both")
DEBUG_PER_PARTITION = 2
EXIT_MISSING = 78
SEED = 0

REQUIRED_FILES = (
    "upstream/equiformer_v2/main_oc20.py",
    "equiformer_v2_153M_all_md.pt",
    "oc20_initial_structures.lmdb",
    "relaxation.yml",
)
REQUIRED_MODULES = ("ocpmodels", "e3nn", "ase", "lmdb")
AUX_MODULES = ("torch", "numpy", "yaml", "pandas", "pyarrow")


# ----------------------------------------------------------------------------- helpers

def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def safe_name(sid):
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(sid))[:120]


def find_file(root, rel):
    p = root / rel
    if p.is_file():
        return p
    base = Path(rel).name
    for cand in sorted(root.rglob(base)):
        if cand.is_file():
            return cand
    return None


def _get(rec, *names, default=None):
    if isinstance(rec, dict):
        for n in names:
            if n in rec:
                return rec[n]
    else:
        for n in names:
            if hasattr(rec, n):
                return getattr(rec, n)
    return default


def collect_missing(input_root):
    """Return (missing_list, resolved_dict, cuda_message)."""
    missing = []
    resolved = {}
    if not (input_root / "manifest.json").is_file():
        missing.append(str(input_root / "manifest.json"))
    for rel in REQUIRED_FILES:
        p = find_file(input_root, rel)
        if p is None:
            missing.append(str(input_root / rel))
        else:
            resolved[rel] = str(p)
    ocp_import_error = None
    for m in REQUIRED_MODULES + AUX_MODULES:
        try:
            __import__(m)
        except Exception as exc:  # noqa: BLE001
            missing.append("python module: %s (%s: %s)" % (m, exc.__class__.__name__, exc))
            if m == "ocpmodels":
                ocp_import_error = "%s: %s" % (exc.__class__.__name__, exc)
    # OCPCalculator is the native entry point; verify it is importable when ocpmodels is.
    if "ocpmodels" not in [x.split()[2] for x in missing if x.startswith("python module:")]:
        try:
            from ocpmodels.common.relaxation.ase_utils import OCPCalculator  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            missing.append("ocpmodels.common.relaxation.ase_utils.OCPCalculator (%s: %s)"
                           % (exc.__class__.__name__, exc))
    cuda_msg = "torch not importable"
    try:
        import torch
        if torch.cuda.is_available():
            cuda_msg = "%s (torch %s, cuda %s)" % (
                torch.cuda.get_device_name(0), torch.__version__, torch.version.cuda)
        else:
            cuda_msg = "torch.cuda.is_available() == False"
            missing.append("CUDA GPU: " + cuda_msg)
    except Exception as exc:  # noqa: BLE001
        missing.append("CUDA GPU: " + cuda_msg + " (%s)" % exc)
    return missing, resolved, cuda_msg


# ----------------------------------------------------------------------------- doctor

def cmd_doctor(args):
    input_root = Path(args.input).resolve()
    missing, resolved, cuda_msg = collect_missing(input_root)
    report = {
        "task_id": TASK_ID,
        "command": "doctor",
        "backend": BACKEND,
        "upstream_commit": UPSTREAM_COMMIT,
        "calculator": "ocpmodels.common.relaxation.ase_utils.OCPCalculator",
        "input_root": str(input_root),
        "input_root_exists": input_root.is_dir(),
        "required_files": {rel: resolved.get(rel) for rel in REQUIRED_FILES},
        "required_modules": list(REQUIRED_MODULES),
        "aux_modules": list(AUX_MODULES),
        "cuda": cuda_msg,
        "missing": missing,
        "status": "available" if not missing else "missing-assets",
        "exit_code": 0 if not missing else EXIT_MISSING,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not missing else EXIT_MISSING


# ----------------------------------------------------------------------------- model

def load_calculator(ckpt_path):
    """Return the original OCP ASE calculator bound to the EquiformerV2 153M All+MD
    checkpoint, using the nets/oc20.trainer registered by the upstream main_oc20.py
tree (ocpmodels.common). GPU only."""
    from ocpmodels.common.relaxation.ase_utils import OCPCalculator
    return OCPCalculator(checkpoint_path=str(ckpt_path), cpu=False), "OCPCalculator"


def normalize_relax_cfg(raw):
    r = raw.get("relaxation", raw) if isinstance(raw, dict) else {}
    if not isinstance(r, dict):
        r = {}
    opt = str(r.get("optimizer", "LBFGS")).upper()
    fmax = float(r.get("fmax", 0.03))
    max_steps = int(r.get("max_steps", r.get("maxstep", 200)))
    fixed_tags = r.get("fixed_tags")
    if fixed_tags is None:
        fixed_tags = [0]  # OC20 IS2RS: subsurface / bulk atoms are held fixed
    return {"optimizer": opt, "fmax": fmax, "max_steps": max_steps,
            "fixed_tags": [int(t) for t in fixed_tags], "raw": r}


# ----------------------------------------------------------------------------- structure

def build_atoms(rec):
    import numpy as np
    from ase import Atoms
    pos = np.asarray(_get(rec, "pos", "positions"), dtype=np.float64)
    z = np.asarray(_get(rec, "atomic_numbers", "z", "numbers"), dtype=int)
    cell = _get(rec, "cell", default=None)
    cell = np.asarray(cell, dtype=np.float64).reshape(3, 3) if cell is not None else np.zeros((3, 3))
    tags = _get(rec, "tags", default=None)
    tags = np.asarray(tags, dtype=int) if tags is not None else np.zeros(len(z), dtype=int)
    fixed = _get(rec, "fixed", default=None)
    pbc = bool(np.any(np.abs(cell) > 0.0))
    atoms = Atoms(numbers=z, positions=pos, cell=cell, pbc=pbc, tags=tags)
    return atoms, (np.asarray(fixed, dtype=bool) if fixed is not None else None)


def is2re_lmdb_select(path, per_partition=DEBUG_PER_PARTITION):
    """Return (selection, meta). selection = [(partition, sid, rec), ...]."""
    import lmdb
    env = lmdb.open(str(path), subdir=False, readonly=True, lock=False,
                    readahead=False, meminit=False, max_readers=1)
    meta = {"total_records": 0, "partition_metadata": "absent", "pool": None}
    buckets = {p: [] for p in PARTITIONS}
    other = []
    key_is_sid = True
    with env.begin() as txn:
        for key, val in txn.cursor():
            meta["total_records"] += 1
            try:
                ks = key.decode("utf-8")
            except Exception:  # noqa: BLE001
                ks = None
            if ks is None or len(ks) > 100 or not ks.isprintable():
                key_is_sid = False
                break
        if not key_is_sid:
            with env.begin() as txn:
                for key, val in txn.cursor():
                    rec = pickle.loads(val)
                    part = _get(rec, "dataset", "split", "partition")
                    sid = str(_get(rec, "sid", "fid", "id"))
                    h = hashlib.sha256(sid.encode()).hexdigest()
                    if part is None:
                        other.append((h, sid, key))
                    else:
                        part = str(part)
                        buckets.setdefault(part, []).append((h, sid, key))
        else:
            with env.begin() as txn:
                for key, val in txn.cursor():
                    sid = key.decode("utf-8")
                    h = hashlib.sha256(sid.encode()).hexdigest()
                    other.append((h, sid, key))
    if any(buckets.get(p) for p in PARTITIONS):
        meta["partition_metadata"] = "present"
    selection_meta = []
    for p in PARTITIONS:
        for h, sid, key in sorted(buckets.get(p, []), key=lambda t: t[0])[:per_partition]:
            selection_meta.append((p, sid, key))
    if not selection_meta:
        meta["partition_metadata"] = "absent"
        meta["pool"] = "renamed-from-top-sha256"
        for i, (h, sid, key) in enumerate(sorted(other, key=lambda t: t[0])[:per_partition * 4]):
            selection_meta.append((PARTITIONS[i // per_partition], sid, key))
    out = []
    with env.begin() as txn:
        for p, sid, key in selection_meta:
            raw = txn.get(key)
            if raw is None:
                continue
            rec = raw if isinstance(raw, dict) else pickle.loads(raw)
            out.append((p, sid, rec))
    env.close()
    return out, meta


# ----------------------------------------------------------------------------- relaxation

def make_optimizer(name, atoms, logfile):
    from ase.optimize import BFGS, FIRE, LBFGS
    cls = {"FIRE": FIRE, "LBFGS": LBFGS, "BFGS": BFGS}.get(str(name).upper(), LBFGS)
    return cls(atoms, logfile=str(logfile), trajectory=None)


class RelaxRecorder:
    """Collects per-step energy and maximum force on the free (non-fixed) atoms."""

    def __init__(self, atoms, free_mask, trajectory_path):
        import numpy as np
        from ase.io import Trajectory
        self.atoms = atoms
        self.free_mask = np.asarray(free_mask)
        self.steps = []
        self.traj = Trajectory(str(trajectory_path), "w", atoms)

    def __call__(self):
        import numpy as np
        e = float(self.atoms.get_potential_energy())
        f = np.asarray(self.atoms.get_forces())
        if self.free_mask.any():
            mx = float(np.linalg.norm(f[self.free_mask], axis=1).max())
        else:
            mx = 0.0
        self.steps.append({"step": len(self.steps), "energy": e, "max_force_free": mx})
        self.traj.write()

    def close(self):
        try:
            self.traj.close()
        except Exception:  # noqa: BLE001
            pass


def relax_system(partition, sid, rec, calc, cfg, work_dir, steps_done=0):
    import numpy as np
    from ase.constraints import FixAtoms
    from ase.io import write

    atoms, rec_fixed = build_atoms(rec)
    init_pos = atoms.get_positions().copy()
    init_z = atoms.get_atomic_numbers().copy()
    init_cell = atoms.get_cell().array.copy()

    atoms.calc = calc
    if rec_fixed is not None and rec_fixed.shape[0] == len(atoms):
        fixed_mask = rec_fixed.copy()
        fix_source = "lmdb.fixed"
    else:
        fixed_mask = np.fromiter((t in set(cfg["fixed_tags"]) for t in atoms.get_tags()),
                                 dtype=bool, count=len(atoms))
        fix_source = "fixed_tags=%s" % cfg["fixed_tags"]
    free_mask = ~fixed_mask
    if fixed_mask.any():
        atoms.set_constraint(FixAtoms(mask=fixed_mask))

    sname = safe_name(sid)
    sdir = work_dir / sname
    sdir.mkdir(parents=True, exist_ok=True)
    restart_path = sdir / "optimizer.restart"
    final_path = sdir / "final.extxyz"

    t_eval0 = time.time()
    initial_energy = float(atoms.get_potential_energy())
    initial_forces = np.asarray(atoms.get_forces())
    eval_s0 = time.time() - t_eval0

    optimizer = make_optimizer(cfg["optimizer"], atoms, sdir / "opt.log")
    remaining = max(0, int(cfg["max_steps"]) - int(steps_done))
    if steps_done and restart_path.is_file():
        try:
            optimizer.load(str(restart_path))
        except Exception:  # noqa: BLE001
            pass

    recorder = RelaxRecorder(atoms, free_mask, sdir / "trajectory.extxyz")
    for i in range(steps_done):
        recorder.steps.append({"step": i, "energy": None, "max_force_free": None})
    if steps_done == 0:
        recorder()
    optimizer.attach(recorder)

    t_opt0 = time.time()
    error = None
    converged = False
    try:
        if remaining > 0:
            optimizer.run(fmax=float(cfg["fmax"]), steps=remaining)
        converged = bool(optimizer.converged())
    except Exception:  # noqa: BLE001
        error = traceback.format_exc()
        converged = False
    opt_s = time.time() - t_opt0
    recorder.close()

    try:
        optimizer.dump(str(restart_path))
    except Exception:  # noqa: BLE001
        pass

    t_eval1 = time.time()
    final_energy = float(atoms.get_potential_energy())
    final_forces = np.asarray(atoms.get_forces())
    eval_s = eval_s0 + (time.time() - t_eval1)
    if free_mask.any():
        max_free = float(np.linalg.norm(final_forces[free_mask], axis=1).max())
    else:
        max_free = 0.0

    fixed_moved = 0.0
    if fixed_mask.any():
        fixed_moved = float(np.abs(atoms.get_positions() - init_pos)[fixed_mask].max())
    cell_delta = float(np.abs(atoms.get_cell().array - init_cell).max())
    z_same = bool(np.array_equal(atoms.get_atomic_numbers(), init_z))

    atoms.info.update({"sid": str(sid), "partition": str(partition),
                       "converged": int(bool(converged)), "max_force_free": max_free})
    write(str(final_path), atoms)
    write(str(work_dir.parent / "relaxed_structures.extxyz"), atoms, append=True)

    executed = len([s for s in recorder.steps if s.get("step", -1) >= steps_done])
    return {
        "sid": str(sid),
        "partition": str(partition),
        "n_atoms": int(len(atoms)),
        "n_fixed": int(fixed_mask.sum()),
        "n_free": int(free_mask.sum()),
        "fix_source": fix_source,
        "steps_done": int(steps_done + executed),
        "converged": bool(converged),
        "initial_energy_eV": initial_energy,
        "final_energy_eV": final_energy,
        "max_force_free_eV_per_A": max_free,
        "initial_max_force_free_eV_per_A":
            float(np.linalg.norm(initial_forces[free_mask], axis=1).max()) if free_mask.any() else 0.0,
        "fixed_atom_max_displacement_A": fixed_moved,
        "cell_max_delta_A": cell_delta,
        "atomic_numbers_unchanged": z_same,
        "opt_wall_s": opt_s,
        "eval_wall_s": eval_s,
        "final_structure": str(final_path),
        "error": error,
    }


# ----------------------------------------------------------------------------- run/resume

def _save_ranking(results, out_path):
    groups = {}
    for r in results:
        groups.setdefault(r["partition"], []).append(r)
    ranking = {}
    for part, rows in groups.items():
        ordered = sorted(rows, key=lambda r: r.get("final_energy_eV", float("inf")))
        ranking[part] = [{"rank": i + 1, "sid": r["sid"],
                          "final_energy_eV": r.get("final_energy_eV"),
                          "converged": bool(r.get("converged"))}
                         for i, r in enumerate(ordered)]
    Path(out_path).write_text(json.dumps(ranking, indent=2, ensure_ascii=False))
    return ranking


def _save_parquet(results, out_path):
    import pandas as pd
    rows = []
    for r in results:
        rows.append({
            "sid": r["sid"], "partition": r["partition"],
            "step": int(r.get("steps_done", 0)),
            "convergence": bool(r.get("converged")),
            "initial_energy_eV": r.get("initial_energy_eV"),
            "final_energy_eV": r.get("final_energy_eV"),
            "initial_max_force_free_eV_per_A": r.get("initial_max_force_free_eV_per_A"),
            "max_force_free_eV_per_A": r.get("max_force_free_eV_per_A"),
            "n_atoms": r.get("n_atoms"), "n_fixed": r.get("n_fixed"),
            "n_free": r.get("n_free"),
            "fixed_atom_max_displacement_A": r.get("fixed_atom_max_displacement_A"),
            "cell_max_delta_A": r.get("cell_max_delta_A"),
            "atomic_numbers_unchanged": r.get("atomic_numbers_unchanged"),
            "opt_wall_s": r.get("opt_wall_s"), "eval_wall_s": r.get("eval_wall_s"),
            "final_structure": r.get("final_structure"),
        })
    pd.DataFrame(rows).to_parquet(out_path, index=False)


def _prepare_run(args):
    """Common gate for run/resume: CUDA, inputs, config. Returns dict or (None, exit_code)."""
    input_root = Path(args.input).resolve()
    output_root = Path(args.output).resolve()
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
    except Exception:  # noqa: BLE001
        cuda_ok = False
    if not cuda_ok:
        print(json.dumps({"status": "cuda-unavailable",
                          "detail": "CUDA GPU is required; refusing CPU fallback."}, indent=2))
        return None, 2
    missing, resolved, cuda_msg = collect_missing(input_root)
    if missing:
        print(json.dumps({"status": "missing-inputs", "missing": missing,
                          "detail": "Refusing to start: no genuine assets, no fabricated inputs."},
                         indent=2, ensure_ascii=False))
        return None, EXIT_MISSING
    import yaml
    raw_cfg = yaml.safe_load(Path(resolved["relaxation.yml"]).read_text())
    cfg = normalize_relax_cfg(raw_cfg)
    return {"input_root": input_root, "output_root": output_root,
            "resolved": resolved, "cfg": cfg, "cuda_msg": cuda_msg}, 0


def cmd_run(args):
    prep, code = _prepare_run(args)
    if prep is None:
        return code

    import numpy as np
    import torch

    t_start = time.time()
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    np.random.seed(SEED)

    input_root, output_root, resolved, cfg = (prep["input_root"], prep["output_root"],
                                              prep["resolved"], prep["cfg"])
    output_root.mkdir(parents=True, exist_ok=True)
    work_root = output_root / "work"
    work_root.mkdir(exist_ok=True)
    extxyz_path = output_root / "relaxed_structures.extxyz"
    if extxyz_path.exists():
        extxyz_path.unlink()

    t_load0 = time.time()
    calc, calc_kind = load_calculator(resolved["equiformer_v2_153M_all_md.pt"])
    load_model_s = time.time() - t_load0

    t_sel0 = time.time()
    selection, lmdb_meta = is2re_lmdb_select(resolved["oc20_initial_structures.lmdb"],
                                             DEBUG_PER_PARTITION)
    select_s = time.time() - t_sel0

    if not selection:
        result = {"task_id": TASK_ID, "backend": BACKEND, "status": "no-records-selected",
                  "lmdb": lmdb_meta}
        (output_root / "run.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 1

    results = []
    t_relax0 = time.time()
    for partition, sid, rec in selection:
        try:
            row = relax_system(partition, sid, rec, calc, cfg, work_root)
        except Exception:  # noqa: BLE001
            row = {"sid": str(sid), "partition": str(partition), "converged": False,
                   "n_atoms": 0, "n_fixed": 0, "n_free": 0, "steps_done": 0,
                   "initial_energy_eV": float("nan"), "final_energy_eV": float("nan"),
                   "initial_max_force_free_eV_per_A": float("nan"),
                   "max_force_free_eV_per_A": float("nan"),
                   "fixed_atom_max_displacement_A": float("nan"),
                   "cell_max_delta_A": float("nan"),
                   "atomic_numbers_unchanged": False, "opt_wall_s": 0.0,
                   "eval_wall_s": 0.0, "final_structure": None,
                   "error": traceback.format_exc()}
        results.append(row)
        print("[%s] sid=%s converged=%s E=%.6f maxF=%.4f" % (
            row.get("partition"), row.get("sid"), row.get("converged"),
            row.get("final_energy_eV", float("nan")),
            row.get("max_force_free_eV_per_A", float("nan"))), flush=True)
    relax_s = time.time() - t_relax0

    ranking = _save_ranking(results, output_root / "ranking.json")
    _save_parquet(results, output_root / "energies.parquet")

    state = {"steps_done": {r["sid"]: r["steps_done"] for r in results},
             "non_converged": [{"sid": r["sid"], "partition": r["partition"],
                                "steps_done": r["steps_done"],
                                "final_structure": r.get("final_structure")}
                               for r in results if not r["converged"]],
             "max_steps": cfg["max_steps"], "fmax": cfg["fmax"],
             "optimizer": cfg["optimizer"], "fixed_tags": cfg["fixed_tags"]}
    (output_root / "resume_state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False))

    config_dump = {"task_id": TASK_ID, "backend": BACKEND,
                    "upstream_commit": UPSTREAM_COMMIT, "seed": SEED,
                    "calculator": calc_kind,
                    "relaxation": {k: cfg[k] for k in ("optimizer", "fmax", "max_steps", "fixed_tags")},
                    "device": prep["cuda_msg"],
                    "input_files": resolved,
                    "input_sha256": {k: sha256_file(v) for k, v in resolved.items()},
                    "lmdb": lmdb_meta, "debug_per_partition": DEBUG_PER_PARTITION}
    (output_root / "config.json").write_text(json.dumps(config_dump, indent=2, ensure_ascii=False))

    run_json = {
        "task_id": TASK_ID,
        "backend": BACKEND,
        "upstream_commit": UPSTREAM_COMMIT,
        "scale": "native_debug",
        "command": "run",
        "status": "completed",
        "device": prep["cuda_msg"],
        "seed": SEED,
        "calculator": calc_kind,
        "relaxation": {k: cfg[k] for k in ("optimizer", "fmax", "max_steps", "fixed_tags")},
        "num_systems": len(results),
        "num_converged": sum(1 for r in results if r["converged"]),
        "timings_s": {"model_load": load_model_s, "selection": select_s,
                      "relaxation": relax_s, "total": time.time() - t_start},
        "device_memory_peak_gib": torch.cuda.max_memory_allocated() / (1 << 30),
        "lmdb": lmdb_meta,
        "systems": results,
        "ranking": ranking,
        "outputs": ["relaxed_structures.extxyz", "energies.parquet", "ranking.json",
                    "config.json", "resume_state.json", "run.json"],
    }
    (output_root / "run.json").write_text(json.dumps(run_json, indent=2, ensure_ascii=False))
    print(json.dumps({"status": "completed", "num_systems": len(results),
                      "num_converged": run_json["num_converged"],
                      "timings_s": run_json["timings_s"]}, indent=2))
    return 0


def cmd_resume(args):
    prep, code = _prepare_run(args)
    if prep is None:
        return code

    import numpy as np
    import torch
    from ase.io import read, write
    from ase.constraints import FixAtoms
    from ase.optimize import BFGS, FIRE, LBFGS

    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)

    output_root = prep["output_root"]
    state_path = output_root / "resume_state.json"
    if not state_path.is_file():
        print(json.dumps({"status": "nothing-to-resume",
                          "detail": "%s not found" % state_path}, indent=2))
        return EXIT_MISSING
    state = json.loads(state_path.read_text())
    if not state.get("non_converged"):
        print(json.dumps({"status": "already-converged", "detail": "all systems converged"}, indent=2))
        return 0

    cfg = prep["cfg"]
    resolved = prep["resolved"]
    work_root = output_root / "work"
    calc, calc_kind = load_calculator(resolved["equiformer_v2_153M_all_md.pt"])

    selection, lmdb_meta = is2re_lmdb_select(resolved["oc20_initial_structures.lmdb"],
                                             DEBUG_PER_PARTITION)
    by_sid = {sid: (part, rec) for part, sid, rec in selection}

    t0 = time.time()
    prior = json.loads((output_root / "run.json").read_text()) if (output_root / "run.json").is_file() else {"systems": []}
    prior_by_sid = {r["sid"]: r for r in prior.get("systems", [])}

    for item in state["non_converged"]:
        sid = item["sid"]
        if sid not in by_sid:
            print("skip %s: not in current selection" % sid)
            continue
        part, rec = by_sid[sid]
        src = item.get("final_structure")
        if not src or not Path(src).is_file():
            print("skip %s: no saved geometry" % sid)
            continue
        atoms = read(src)
        atoms.calc = calc
        fixed_tags = set(cfg["fixed_tags"])
        fixed_mask = np.fromiter((t in fixed_tags for t in atoms.get_tags()),
                                 dtype=bool, count=len(atoms))
        if fixed_mask.any():
            atoms.set_constraint(FixAtoms(mask=fixed_mask))
        cls = {"FIRE": FIRE, "LBFGS": LBFGS, "BFGS": BFGS}.get(cfg["optimizer"], LBFGS)
        sdir = work_root / safe_name(sid)
        sdir.mkdir(parents=True, exist_ok=True)
        opt = cls(atoms, logfile=str(sdir / "opt_resume.log"), trajectory=None)
        restart = sdir / "optimizer.restart"
        if restart.is_file():
            try:
                opt.load(str(restart))
            except Exception:  # noqa: BLE001
                pass
        done = int(state["steps_done"].get(sid, 0))
        remaining = max(0, int(state["max_steps"]) - done)
        try:
            if remaining > 0:
                opt.run(fmax=float(state["fmax"]), steps=remaining)
            conv = bool(opt.converged())
        except Exception:  # noqa: BLE001
            conv = False
        try:
            opt.dump(str(restart))
        except Exception:  # noqa: BLE001
            pass
        f = np.asarray(atoms.get_forces())
        mf = float(np.linalg.norm(f[~fixed_mask], axis=1).max()) if (~fixed_mask).any() else 0.0
        atoms.info.update({"sid": sid, "partition": part, "converged": int(conv),
                           "max_force_free": mf})
        write(str(sdir / "final.extxyz"), atoms)
        row = prior_by_sid.get(sid, {"sid": sid, "partition": part, "n_atoms": len(atoms)})
        row.update({"converged": conv, "steps_done": int(state["max_steps"]),
                    "final_energy_eV": float(atoms.get_potential_energy()),
                    "max_force_free_eV_per_A": mf})
        prior_by_sid[sid] = row
        print("resumed %s converged=%s" % (sid, conv), flush=True)

    rows = list(prior_by_sid.values())
    _save_ranking(rows, output_root / "ranking_resume.json")
    try:
        _save_parquet(rows, output_root / "energies_resume.parquet")
    except Exception:  # noqa: BLE001
        pass
    still = [r for r in rows if not r.get("converged")]
    state["non_converged"] = [{"sid": r["sid"], "partition": r["partition"],
                               "steps_done": r.get("steps_done", state["max_steps"]),
                               "final_structure": str(work_root / safe_name(r["sid"]) / "final.extxyz")}
                              for r in still]
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(json.dumps({"status": "resumed", "still_non_converged": len(still),
                      "wall_s": time.time() - t0}, indent=2))
    return 0


# ----------------------------------------------------------------------------- cli

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-F04: OC20 EquiformerV2 153M All+MD catalytic adsorption relaxation "
                    "(native ocpmodels OCPCalculator).")
    sub = parser.add_subparsers(dest="command")

    p_doc = sub.add_parser("doctor", help="Inspect inputs/dependencies; exit 78 if missing.")
    p_doc.add_argument("--input", required=True, help="Read-only input directory.")
    p_doc.set_defaults(func=cmd_doctor)

    p_run = sub.add_parser("run", help="Run the real GPU relaxation.")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)
    p_run.set_defaults(func=cmd_run)

    p_res = sub.add_parser("resume", help="Continue saved non-converged systems.")
    p_res.add_argument("--input", required=True)
    p_res.add_argument("--output", required=True)
    p_res.set_defaults(func=cmd_resume)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
