# GPUv1-F05 (debug variant) - OpenMM CUDA MD on solvated ubiquitin

Real, stateful molecular dynamics on the RCSB 1UBQ ubiquitin system using
**OpenMM 8.6.1 + CUDA plugin** on the real GPU. This is the declared
`debug_only` variant of the reference HECBioSim / GROMACS task: a different
physical system (solvated ubiquitin instead of the 465 399-atom hEGFR dimer)
and a different engine, but a real energy-minimization + NVE integration with
a genuine binary OpenMM restart checkpoint.

## Files in `input/` (fixed by `input/manifest.json`)

| file | role |
| --- | --- |
| `initial.pdb` | 14 923-atom solvated Topology / coordinates |
| `system.xml` | serialized `openmm.System` (amber14-all + tip3pfb) |
| `positions_nm.npy` | (N, 3) float64 starting positions in nm |
| `protein_atom_ids.npy` | 0- (or 1-) indexed protein atom ids |
| `manifest.json` | source / hash record |

## Commands

### `doctor` - inspect inputs and dependencies only (no simulation)

```
python solution/main.py doctor --input input
```

Returns **78** on any missing file / hash mismatch / absent CUDA platform,
**0** otherwise. Never loads a model or runs MD.

### `run` - 200-step NVE MD

```
python solution/main.py run --input input --output output
```

Pipeline:

1. Load `system.xml` via `openmm.XmlSerializer`.
2. Build the NVE integrator through `make_integrator()`:
   `VerletIntegrator(2 fs)` with `setConstraintTolerance(1e-6)` **on the
   integrator** before the `Context` is created. In OpenMM 8.6.1 the
   constraint distance tolerance is an integrator property; the helper is
   shared by `run` and `resume`.
3. Build a `Simulation` on `Platform.getPlatformByName('CUDA')` with default
   properties `Precision=mixed`, `DeviceIndex=0`, `DeterministicForces=true`.
   Explicitly asserts the live `Context` platform is CUDA (no CPU fallback).
4. `context.setPositions(...)` from `positions_nm.npy`, then
   `sim.minimizeEnergy(maxIterations=100)` - real GPU minimization.
5. `context.setVelocitiesToTemperature(300 K, seed=2026)`.
6. Advance 200 Verlet steps of 2 fs (0 -> 0.4 ps), recording every 20 steps
   positions, velocities, time, PE, KE for **all** atoms.

Outputs to `output/`:

* `trajectory.npz` - `positions` `(11, N, 3)` nm, `velocities` `(11, N, 3)`
  nm/ps, `time` in ps, PE/KE/total in kJ/mol. All frames **unwrapped**.
* `energies.json` - per-frame energies plus minimization before/after.
* `system.xml`, `initial.pdb`, `protein_atom_ids.npy` - bit-identical
  copies of the inputs used (checked by `doctor` hashes).
* `state.xml` - final `openmm.State` serialized **unwrapped**
  (`enforcePeriodicBox=False`), i.e. same convention as the trajectory.
  Periodic box vectors are still present in the serialized state.
* `checkpoint.chk` - real binary OpenMM restart state (positions,
  velocities, box vectors, integrator RNG state).
* `run.json` - CUDA platform name, requested default properties, atom count,
  step/interval counts, integrator identity, unit map, finite checks,
  state-vs-last-frame deviation (positions, velocities, time), wall time,
  and a descriptive RMSD of the protein atoms.

## Coordinate convention (fixed)

Both the recorder and the final `state.xml`/`checkpoint.chk` now use
**unwrapped** coordinates (`enforcePeriodicBox=False`). This is the default,
physically-natural convention produced by integration and makes `state.xml`
bit-compatible with the last trajectory frame. `run` enforces this with a
hard `STATE_FRAME_TOL_NM = 1e-9` check and aborts if the two diverge; no
weakened validation is used. Periodic box information is still carried by the
checkpoint and state serializations.

### `resume` - continue from the checkpoint

```
python solution/main.py resume \
    --checkpoint output/checkpoint.chk \
    --artifacts  output \
    --steps 50 \
    --output output/continued
```

Uses the original `system.xml` + `initial.pdb` from `--artifacts`, builds a
fresh `VerletIntegrator(2 fs)` with `setConstraintTolerance(1e-6)`, calls
`loadCheckpoint`. **No minimization, no velocity reinitialization.** It first
verifies (unwrapped, same convention):

* checkpoint positions / velocities are finite and match `atoms`,
* checkpoint positions match the last recorded frame of
  `artifacts/trajectory.npz` to <= 1e-9 nm,
* checkpoint time matches the last recorded time to <= 1e-6 ps.

Then it advances 50 more Verlet steps of 2 fs on CUDA, recording every 10
steps, ending at 0.5 ps. Outputs mirror the `run` command; `run.json` adds the
continuity record and energy drift statistics. `state.xml` written by resume
uses the same unwrapped convention.

## Honest limitations

* Delivered segment: 0.4 ps (`run`) + 0.1 ps (`resume`). This is a smoke test
  of the stateful MD pipeline, **not** a full 1 ns trajectory and **not**
  enough sampling to claim equilibrium or long-time dynamics.
* The reference-large specification (`hEGFR 465 399 atoms / GROMACS / 1 ns`)
  is **not** implemented here. This is the declared `debug_only` variant.
* RMSD in `run.json` is a single-number descriptor of a 0.4 ps window; it
  cannot characterise protein conformational change.
* If the OpenMM CUDA plugin is unavailable or reports a missing shared
  library, `run` and `resume` fail loudly; nothing falls back to the CPU or
  Reference platform.
* No hyperparameter search, no ensembles, no mock weights, no random
  substitutes - one required run/step sequence per command.
