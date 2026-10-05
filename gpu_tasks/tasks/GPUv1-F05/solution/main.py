#!/usr/bin/env python3
"""GPUv1-F05 (debug variant) - OpenMM 8.6.1 CUDA MD on solvated ubiquitin (1UBQ).

Subcommands:
  doctor  --input DIR                                check inputs + dependencies
  run     --input DIR --output DIR                   200-step NVE MD, real CUDA
  resume  --checkpoint F --artifacts DIR --steps N --output DIR

Physics (per TASK.md):
  * energy minimization, at most 100 iterations
  * velocities at 300 K with seed=2026
  * VerletIntegrator NVE, dt=2 fs, constraint tolerance=1e-6
  * 200 steps, record every 20 steps (positions, velocities, time, PE, KE)
  * CUDA platform, mixed precision, DeviceIndex=0, DeterministicForces=true

Coordinate convention (fixed):
  * ALL saved positions (trajectory frames, state.xml, and the binary
    checkpoint) use UNWRAPPED coordinates, obtained with
    enforcePeriodicBox=False. The periodic box vectors are still preserved
    (checkpoint always carries them, and state.xml carries them too).
  * The recorder, the final state.xml, and the resume continuity checks all
    use enforcePeriodicBox=False, so state.xml is bit-compatible with the
    last recorded trajectory frame.
"""
import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

EXPECTED_HASHES = {
    'initial.pdb': 'fd2a8c83a1eee6531f241945d977b59ff8bb03daed7a0acdf505fd8b7695e22d',
    'positions_nm.npy': 'f78816c92f3286d81c8a3190ae4348a708869ff6949510e167415918377fa4dd',
    'system.xml': 'a6d92703887d5b768421cd8f181c8956ee7626d8bc142347b869d1dc1cdef9b2',
    'protein_atom_ids.npy': '4feaf17a2816fca2fa82b08637fe3bba91dd58f0e41eb3d9a7e961e4e51ceaf4',
}
REQUIRED_INPUTS = ['initial.pdb', 'positions_nm.npy', 'system.xml', 'protein_atom_ids.npy']
CUDA_PROPS = {'Precision': 'mixed', 'DeviceIndex': '0', 'DeterministicForces': 'true'}
DT_FS = 2.0
CONSTRAINT_TOL = 1e-6
TEMPERATURE_K = 300.0
SEED = 2026
TOTAL_STEPS = 200
RECORD_INTERVAL = 20
# Strict tolerance for checking that the serialized state matches the last
# recorded trajectory frame (both unwrapped). Identical coordinates should
# agree to ~0 nm; we allow only floating point noise.
STATE_FRAME_TOL_NM = 1e-9


def sha256_file(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_cuda_platform():
    from openmm import Platform
    names = [Platform.getPlatform(i).getName() for i in range(Platform.getNumPlatforms())]
    if 'CUDA' not in names:
        raise RuntimeError(f"CUDA platform unavailable; registered platforms: {names}")
    return Platform.getPlatformByName('CUDA')


def make_integrator(dt_fs=DT_FS, tol=CONSTRAINT_TOL):
    """Build the NVE Verlet integrator with an explicit constraint tolerance.

    In OpenMM 8.6.1 the constraint distance tolerance is an integrator
    property and must be set on the integrator instance before the Context
    is created, so both `run` and `resume` call this helper and pass the
    returned object to Simulation(...).
    """
    from openmm import VerletIntegrator, unit
    integrator = VerletIntegrator(dt_fs * unit.femtoseconds)
    if not hasattr(integrator, 'setConstraintTolerance'):
        raise RuntimeError(
            "VerletIntegrator has no setConstraintTolerance; unsupported OpenMM API")
    integrator.setConstraintTolerance(float(tol))
    return integrator


def make_recorder(ctx):
    """Return a recorder that samples UNWRAPPED (enforcePeriodicBox=False)
    positions/velocities for every atom plus time and PE/KE."""
    from openmm import unit
    frames = {'positions': [], 'velocities': [], 'time': [], 'potential': [], 'kinetic': []}

    def rec():
        st = ctx.getState(getPositions=True, getVelocities=True, getEnergy=True,
                          enforcePeriodicBox=False)
        frames['positions'].append(
            np.array(st.getPositions().value_in_unit(unit.nanometer), dtype='float64'))
        frames['velocities'].append(
            np.array(st.getVelocities().value_in_unit(unit.nanometer / unit.picosecond),
                     dtype='float64'))
        frames['time'].append(float(st.getTime().value_in_unit(unit.picosecond)))
        frames['potential'].append(
            float(st.getPotentialEnergy().value_in_unit(unit.kilojoule / unit.mole)))
        frames['kinetic'].append(
            float(st.getKineticEnergy().value_in_unit(unit.kilojoule / unit.mole)))

    return frames, rec


def kabsch_rmsd(P, Q):
    Pc = P - P.mean(0, keepdims=True)
    Qc = Q - Q.mean(0, keepdims=True)
    H = Pc.T @ Qc
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, 1.0, d])
    R = Vt.T @ D @ U.T
    Pr = Pc @ R.T
    return float(np.sqrt(((Pr - Qc) ** 2).sum(1).mean()))


# ----------------------------------------------------------------------------- doctor
def cmd_doctor(args):
    inp = Path(args.input)
    problems, notes = [], []
    if not inp.is_dir():
        print(f"doctor: FAILED - input directory not found: {inp}")
        return 78
    if not (inp / 'manifest.json').exists():
        notes.append(f"note: manifest.json absent in {inp}")
    for name in REQUIRED_INPUTS:
        p = inp / name
        if not p.exists():
            problems.append(f"missing file: {p}")
        else:
            exp = EXPECTED_HASHES.get(name)
            if exp:
                try:
                    got = sha256_file(p)
                except Exception as e:
                    problems.append(f"cannot hash {p}: {e}")
                    continue
                if got != exp:
                    problems.append(f"hash mismatch for {name}: {got} != {exp}")
    try:
        import numpy as _np  # noqa
        notes.append(f"numpy {_np.__version__}")
    except Exception as e:
        problems.append(f"numpy import failed: {e}")
    try:
        import openmm
        notes.append(f"openmm {openmm.version.version}")
    except Exception as e:
        problems.append(f"openmm import failed: {e}")
    else:
        try:
            from openmm import Platform
            names = [Platform.getPlatform(i).getName() for i in range(Platform.getNumPlatforms())]
            if 'CUDA' not in names:
                problems.append(f"CUDA platform not registered; platforms: {names}")
            else:
                notes.append(f"platforms: {names}")
        except Exception as e:
            problems.append(f"platform query failed: {e}")
    for n in notes:
        print(f"doctor: info - {n}")
    if problems:
        print("doctor: FAILED")
        for p in problems:
            print(f"doctor: missing - {p}")
        return 78
    print("doctor: OK")
    return 0


# -------------------------------------------------------------------------------- run
def cmd_run(args):
    import openmm
    from openmm import unit
    from openmm.app import PDBFile, Simulation

    inp = Path(args.input)
    out = Path(args.output)

    missing = [str(inp / n) for n in REQUIRED_INPUTS if not (inp / n).exists()]
    if missing:
        print("run: missing inputs:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 78
    out.mkdir(parents=True, exist_ok=True)

    with open(inp / 'system.xml') as f:
        system = openmm.XmlSerializer.deserialize(f.read())
    n_atoms = system.getNumParticles()

    positions = np.load(str(inp / 'positions_nm.npy')).astype('float64')
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError(f"positions_nm.npy must be (N,3); got {positions.shape}")
    if positions.shape[0] != n_atoms:
        raise ValueError(f"positions rows {positions.shape[0]} != system atoms {n_atoms}")
    if not np.isfinite(positions).all():
        raise ValueError("input positions contain non-finite values")

    pdb = PDBFile(str(inp / 'initial.pdb'))
    if pdb.topology.getNumAtoms() != n_atoms:
        raise ValueError(f"PDB atoms {pdb.topology.getNumAtoms()} != system atoms {n_atoms}")

    platform = load_cuda_platform()
    integrator = make_integrator()
    sim = Simulation(pdb.topology, system, integrator, platform, CUDA_PROPS)
    ctx = sim.context
    if ctx.getPlatform().getName() != 'CUDA':
        raise RuntimeError(f"expected CUDA platform, got {ctx.getPlatform().getName()}")

    ctx.setPositions(unit.Quantity(positions, unit.nanometer))
    e_min_before = float(ctx.getState(getEnergy=True).getPotentialEnergy()
                         .value_in_unit(unit.kilojoule / unit.mole))
    t0 = time.time()
    sim.minimizeEnergy(maxIterations=100)
    t_min = time.time() - t0
    e_min_after = float(ctx.getState(getEnergy=True).getPotentialEnergy()
                        .value_in_unit(unit.kilojoule / unit.mole))

    ctx.setVelocitiesToTemperature(TEMPERATURE_K * unit.kelvin, SEED)

    frames, rec = make_recorder(ctx)
    rec()
    t0 = time.time()
    for _ in range(TOTAL_STEPS // RECORD_INTERVAL):
        sim.step(RECORD_INTERVAL)
        rec()
    t_md = time.time() - t0

    P = np.array(frames['positions'], dtype='float64')
    V = np.array(frames['velocities'], dtype='float64')
    T = np.array(frames['time'], dtype='float64')
    PE = np.array(frames['potential'], dtype='float64')
    KE = np.array(frames['kinetic'], dtype='float64')

    np.savez(str(out / 'trajectory.npz'),
             positions=P, velocities=V, time=T,
             potential_energy=PE, kinetic_energy=KE, total_energy=PE + KE,
             units={'positions': 'nm', 'velocities': 'nm/ps', 'time': 'ps', 'energy': 'kJ/mol'},
             coordinate_convention='unwrapped',
             atoms=n_atoms, steps=TOTAL_STEPS, dt_fs=DT_FS,
             interval_steps=RECORD_INTERVAL, temperature_K=TEMPERATURE_K, seed=SEED)

    # Final state and checkpoint use the SAME unwrapped convention as the
    # trajectory frames, so state.xml must agree with trajectory[-1].
    st_final = ctx.getState(getPositions=True, getVelocities=True, getEnergy=True,
                            enforcePeriodicBox=False)
    with open(out / 'state.xml', 'wb') as f:
        f.write(openmm.XmlSerializer.serialize(st_final).encode())

    with open(out / 'checkpoint.chk', 'wb') as f:
        sim.saveCheckpoint(f)

    shutil.copy2(str(inp / 'system.xml'), str(out / 'system.xml'))
    shutil.copy2(str(inp / 'initial.pdb'), str(out / 'initial.pdb'))
    if (inp / 'protein_atom_ids.npy').exists():
        shutil.copy2(str(inp / 'protein_atom_ids.npy'), str(out / 'protein_atom_ids.npy'))

    energies = {
        'time_ps': T.tolist(),
        'potential_kJ_mol': PE.tolist(),
        'kinetic_kJ_mol': KE.tolist(),
        'total_kJ_mol': (PE + KE).tolist(),
        'minimization': {
            'max_iterations': 100,
            'potential_before_kJ_mol': e_min_before,
            'potential_after_kJ_mol': e_min_after,
            'wall_s': t_min,
        },
    }
    with open(out / 'energies.json', 'w') as f:
        json.dump(energies, f, indent=2)

    pos_state = np.array(st_final.getPositions().value_in_unit(unit.nanometer), dtype='float64')
    vel_state = np.array(st_final.getVelocities().value_in_unit(unit.nanometer / unit.picosecond),
                         dtype='float64')
    time_state = float(st_final.getTime().value_in_unit(unit.picosecond))
    max_dev_state = float(np.max(np.abs(pos_state - P[-1])))
    max_dev_vel = float(np.max(np.abs(vel_state - V[-1])))
    time_dev = abs(time_state - float(T[-1]))
    finite_pos = bool(np.isfinite(P).all())
    finite_vel = bool(np.isfinite(V).all())

    if not (finite_pos and finite_vel):
        raise RuntimeError("non-finite positions or velocities detected in trajectory")
    if max_dev_state > STATE_FRAME_TOL_NM:
        raise RuntimeError(
            f"state.xml positions differ from last trajectory frame by "
            f"{max_dev_state} nm (coordinate-convention regression)")
    if time_dev > 1e-6:
        raise RuntimeError(
            f"state.xml time {time_state} ps differs from last trajectory "
            f"time {float(T[-1])} ps")

    rmsd_val = None
    n_prot = None
    ids_path = inp / 'protein_atom_ids.npy'
    if ids_path.exists():
        try:
            ids = np.load(str(ids_path)).astype(int).ravel()
            if ids.min() >= 1 and ids.max() >= n_atoms:
                ids = ids - 1
            if ids.min() >= 0 and ids.max() < n_atoms:
                n_prot = int(ids.size)
                rmsd_val = kabsch_rmsd(P[0][ids], P[-1][ids])
            else:
                rmsd_val = 'protein atom ids out of range'
        except Exception as e:
            rmsd_val = f'unavailable: {e}'

    run_json = {
        'task': 'GPUv1-F05',
        'variant': 'debug',
        'mode': 'run',
        'engine': f'OpenMM {openmm.version.version}',
        'platform': ctx.getPlatform().getName(),
        'platform_default_properties': dict(CUDA_PROPS),
        'coordinate_convention': 'unwrapped (enforcePeriodicBox=False) for trajectory, state.xml and checkpoint',
        'atoms': int(n_atoms),
        'protein_atoms': n_prot,
        'steps_total': TOTAL_STEPS,
        'steps_interval': RECORD_INTERVAL,
        'frames': int(P.shape[0]),
        'dt_fs': DT_FS,
        'integrator': 'VerletIntegrator',
        'constraint_tolerance': CONSTRAINT_TOL,
        'temperature_K': TEMPERATURE_K,
        'seed': SEED,
        'units': {'positions': 'nm', 'velocities': 'nm/ps', 'time': 'ps', 'energy': 'kJ/mol'},
        'start_time_ps': float(T[0]),
        'end_time_ps': float(T[-1]),
        'wall_md_s': t_md,
        'wall_min_s': t_min,
        'all_finite_positions': finite_pos,
        'all_finite_velocities': finite_vel,
        'state_vs_last_frame_max_abs_position_nm': max_dev_state,
        'state_vs_last_frame_max_abs_velocity_nm_per_ps': max_dev_vel,
        'state_vs_last_frame_time_dev_ps': time_dev,
        'state_vs_last_frame_tol_nm': STATE_FRAME_TOL_NM,
        'potential_energy_ptp_kJ_mol': float(PE.max() - PE.min()),
        'total_energy_ptp_kJ_mol': float((PE + KE).max() - (PE + KE).min()),
        'rmsd_protein_nm': rmsd_val,
        'rmsd_note': ('Descriptive only - a single 0.4 ps NVE segment over the short '
                      'debug trajectory is not sufficient for long-time dynamics analysis.'),
        'checkpoint': 'checkpoint.chk (binary OpenMM restart state, saveState serialized)',
    }
    with open(out / 'run.json', 'w') as f:
        json.dump(run_json, f, indent=2)

    print(json.dumps({'status': 'ok', 'output': str(out),
                      'time_ps': float(T[-1]), 'frames': int(P.shape[0]),
                      'state_vs_last_frame_max_abs_nm': max_dev_state}))
    return 0


# ----------------------------------------------------------------------------- resume
def cmd_resume(args):
    import openmm
    from openmm import unit
    from openmm.app import PDBFile, Simulation

    art = Path(args.artifacts)
    ckpt = Path(args.checkpoint)
    out = Path(args.output)

    if not ckpt.exists():
        print(f"resume: missing checkpoint {ckpt}", file=sys.stderr)
        return 78
    sysx = art / 'system.xml'
    pdbf = art / 'initial.pdb'
    if not sysx.exists() or not pdbf.exists():
        print(f"resume: missing artifacts in {art}: {sysx} / {pdbf}", file=sys.stderr)
        return 78
    if int(args.steps) <= 0:
        print("resume: --steps must be positive", file=sys.stderr)
        return 78
    out.mkdir(parents=True, exist_ok=True)

    with open(sysx) as f:
        system = openmm.XmlSerializer.deserialize(f.read())
    n_atoms = system.getNumParticles()
    pdb = PDBFile(str(pdbf))
    if pdb.topology.getNumAtoms() != n_atoms:
        raise ValueError("artifacts PDB atoms != system atoms")

    platform = load_cuda_platform()
    integrator = make_integrator()
    sim = Simulation(pdb.topology, system, integrator, platform, CUDA_PROPS)
    ctx = sim.context
    if ctx.getPlatform().getName() != 'CUDA':
        raise RuntimeError(f"expected CUDA platform, got {ctx.getPlatform().getName()}")

    with open(ckpt, 'rb') as f:
        sim.loadCheckpoint(f)

    # Same unwrapped convention as run.
    st0 = ctx.getState(getPositions=True, getVelocities=True, getEnergy=True,
                       enforcePeriodicBox=False)
    t_start = float(st0.getTime().value_in_unit(unit.picosecond))
    P0 = np.array(st0.getPositions().value_in_unit(unit.nanometer), dtype='float64')
    V0 = np.array(st0.getVelocities().value_in_unit(unit.nanometer / unit.picosecond),
                  dtype='float64')
    if P0.shape[0] != n_atoms:
        raise ValueError(f"checkpoint positions rows {P0.shape[0]} != atoms {n_atoms}")
    if not np.isfinite(P0).all() or not np.isfinite(V0).all():
        raise RuntimeError("non-finite state loaded from checkpoint")

    continuity = {'checked': False}
    prev_traj = art / 'trajectory.npz'
    if prev_traj.exists():
        with np.load(str(prev_traj)) as d:
            prev_pos = np.array(d['positions'][-1], dtype='float64')
            prev_vel = np.array(d['velocities'][-1], dtype='float64')
            prev_time = float(np.array(d['time'])[-1])
        max_diff = float(np.max(np.abs(prev_pos - P0)))
        max_vel_diff = float(np.max(np.abs(prev_vel - V0)))
        if max_diff > 1e-9:
            raise RuntimeError(
                f"checkpoint positions differ from last recorded frame by {max_diff} nm")
        if abs(prev_time - t_start) > 1e-6:
            raise RuntimeError(
                f"checkpoint time {t_start} ps != last recorded time {prev_time} ps")
        continuity = {'checked': True, 'prev_last_time_ps': prev_time,
                      'checkpoint_time_ps': t_start,
                      'max_abs_position_diff_nm': max_diff,
                      'max_abs_velocity_diff_nm_per_ps': max_vel_diff,
                      'coordinate_convention': 'unwrapped'}

    frames, rec = make_recorder(ctx)
    rec()
    n_steps = int(args.steps)
    interval = 10
    done = 0
    t0 = time.time()
    while done < n_steps:
        chunk = min(interval, n_steps - done)
        sim.step(chunk)
        done += chunk
        rec()
    t_md = time.time() - t0

    P = np.array(frames['positions'], dtype='float64')
    V = np.array(frames['velocities'], dtype='float64')
    T = np.array(frames['time'], dtype='float64')
    PE = np.array(frames['potential'], dtype='float64')
    KE = np.array(frames['kinetic'], dtype='float64')
    Etot = PE + KE

    if not (np.isfinite(P).all() and np.isfinite(V).all()):
        raise RuntimeError("non-finite positions or velocities detected in resumed trajectory")

    np.savez(str(out / 'trajectory.npz'),
             positions=P, velocities=V, time=T,
             potential_energy=PE, kinetic_energy=KE, total_energy=Etot,
             units={'positions': 'nm', 'velocities': 'nm/ps', 'time': 'ps', 'energy': 'kJ/mol'},
             coordinate_convention='unwrapped',
             atoms=n_atoms, steps=n_steps, dt_fs=DT_FS, interval_steps=interval,
             resume_from_ps=t_start)

    st_final = ctx.getState(getPositions=True, getVelocities=True, getEnergy=True,
                            enforcePeriodicBox=False)
    with open(out / 'state.xml', 'wb') as f:
        f.write(openmm.XmlSerializer.serialize(st_final).encode())
    with open(out / 'checkpoint.chk', 'wb') as f:
        sim.saveCheckpoint(f)

    shutil.copy2(str(sysx), str(out / 'system.xml'))
    shutil.copy2(str(pdbf), str(out / 'initial.pdb'))
    if (art / 'protein_atom_ids.npy').exists():
        shutil.copy2(str(art / 'protein_atom_ids.npy'), str(out / 'protein_atom_ids.npy'))

    with open(out / 'energies.json', 'w') as f:
        json.dump({
            'time_ps': T.tolist(),
            'potential_kJ_mol': PE.tolist(),
            'kinetic_kJ_mol': KE.tolist(),
            'total_kJ_mol': Etot.tolist(),
            'minimization': None,
        }, f, indent=2)

    pos_state = np.array(st_final.getPositions().value_in_unit(unit.nanometer), dtype='float64')
    vel_state = np.array(st_final.getVelocities().value_in_unit(unit.nanometer / unit.picosecond),
                         dtype='float64')
    time_state = float(st_final.getTime().value_in_unit(unit.picosecond))
    max_dev_state = float(np.max(np.abs(pos_state - P[-1])))
    max_dev_vel = float(np.max(np.abs(vel_state - V[-1])))
    time_dev = abs(time_state - float(T[-1]))

    if max_dev_state > STATE_FRAME_TOL_NM:
        raise RuntimeError(
            f"resumed state.xml positions differ from last trajectory frame by "
            f"{max_dev_state} nm")
    if time_dev > 1e-6:
        raise RuntimeError(
            f"resumed state.xml time {time_state} ps differs from last trajectory "
            f"time {float(T[-1])} ps")

    run_json = {
        'task': 'GPUv1-F05',
        'variant': 'debug',
        'mode': 'resume',
        'engine': f'OpenMM {openmm.version.version}',
        'platform': ctx.getPlatform().getName(),
        'platform_default_properties': dict(CUDA_PROPS),
        'coordinate_convention': 'unwrapped (enforcePeriodicBox=False) for trajectory, state.xml and checkpoint',
        'atoms': int(n_atoms),
        'steps_resumed': n_steps,
        'steps_interval': interval,
        'frames': int(P.shape[0]),
        'dt_fs': DT_FS,
        'integrator': 'VerletIntegrator',
        'constraint_tolerance': CONSTRAINT_TOL,
        'minimization_performed': False,
        'velocity_reinitialization': False,
        'start_time_ps': t_start,
        'end_time_ps': float(T[-1]),
        'expected_end_ps': float(t_start + n_steps * DT_FS / 1000.0),
        'wall_md_s': t_md,
        'all_finite_positions': True,
        'all_finite_velocities': True,
        'potential_energy_ptp_kJ_mol': float(PE.max() - PE.min()),
        'total_energy_ptp_kJ_mol': float(Etot.max() - Etot.min()),
        'total_energy_std_kJ_mol': float(Etot.std()),
        'state_vs_last_frame_max_abs_position_nm': max_dev_state,
        'state_vs_last_frame_max_abs_velocity_nm_per_ps': max_dev_vel,
        'state_vs_last_frame_time_dev_ps': time_dev,
        'state_vs_last_frame_tol_nm': STATE_FRAME_TOL_NM,
        'continuity_with_prior_trajectory': continuity,
    }
    with open(out / 'run.json', 'w') as f:
        json.dump(run_json, f, indent=2)

    print(json.dumps({'status': 'ok', 'output': str(out),
                      'start_ps': t_start, 'end_ps': float(T[-1]),
                      'steps': n_steps,
                      'state_vs_last_frame_max_abs_nm': max_dev_state}))
    return 0


# ------------------------------------------------------------------------------- cli
def build_parser():
    p = argparse.ArgumentParser(
        prog='main.py',
        description='GPUv1-F05 (debug variant): OpenMM 8.6.1 CUDA molecular dynamics '
                    'on solvated ubiquitin with real checkpoint/resume support.')
    sub = p.add_subparsers(dest='cmd')

    d = sub.add_parser('doctor', help='check input files and dependencies')
    d.add_argument('--input', required=True, help='input directory (read-only)')

    r = sub.add_parser('run', help='run 200-step Verlet NVE MD on CUDA')
    r.add_argument('--input', required=True, help='input directory')
    r.add_argument('--output', required=True, help='output directory')

    q = sub.add_parser('resume', help='resume from checkpoint and advance N more steps')
    q.add_argument('--checkpoint', required=True, help='checkpoint.chk path')
    q.add_argument('--artifacts', required=True, help='directory with original system.xml/initial.pdb')
    q.add_argument('--steps', type=int, default=50, help='number of additional Verlet steps')
    q.add_argument('--output', required=True, help='output directory for continued run')
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == 'doctor':
        sys.exit(cmd_doctor(args))
    if args.cmd == 'run':
        sys.exit(cmd_run(args))
    if args.cmd == 'resume':
        sys.exit(cmd_resume(args))
    parser.print_help()
    sys.exit(0)


if __name__ == '__main__':
    main()
