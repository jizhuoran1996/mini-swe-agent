# GPUv1-F06 — LAMMPS Ta SNAP Kokkos CUDA adapter

Source-native adapter for the official LAMMPS `examples/snap/in.snap.Ta06A`
workflow: finite-temperature BCC tantalum driven by the Ta06A SNAP+ZBL
potential on a Kokkos CUDA build.

## Entry points

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output [--timeout 3600]
python solution/main.py resume --input input --output output [--timeout 3600]
```

Exit codes: `0` OK, `1` runtime error, `78` missing configuration.

## doctor (no models, no dynamics)

`doctor` inspects, without executing any LAMMPS dynamics:

* every required file listed in `input/manifest.json`
  (`lammps/bin/lmp`, `examples/snap/in.snap.Ta06A`, and the three
  `Ta06A.snap*` potential files) — reports presence, size and SHA-256;
* Python/system dependencies (`numpy`, `nvidia-smi` with a visible GPU);
* binary capabilities via `lmp -h`: `kokkos`, `cuda`/`gpu`, `snap`, `kk`.

Every missing file, dependency or capability is listed under `missing`.
Exit code is `78` if any item is missing, `0` otherwise.

## run

1. Runs `doctor`. If anything is missing it writes
   `output/run.json` with `status: blocked_missing_inputs` and exits `78`.
   **No substitute model (Lennard-Jones), no analytic surrogate, no CPU
   `lmp`, and no fabricated input is ever produced.**
2. Requires a visible CUDA device (`nvidia-smi -L`); aborts otherwise.
3. Copies the upstream `lammps/bin`, `examples/snap` and `potentials` trees
   into a bounded `output/workspace/` (upstream sources are never modified).
4. Adapts the official input in the workspace only: fixes `nrep=4`, adds
   `dump`/`thermo` instrumentation, runs **100 steps**, writes
   `initial.data` and `final.restart`. The SNAP + ZBL pair style and the
   original velocity/NVE/timestep settings are preserved verbatim.
5. Executes `lmp -k on g 1 -sf kk -pk kokkos -in ... -log ...`.

Direct GPU styles (`kk`) are selected exclusively through the binary's
suffix mechanism; there is no CPU fallback path.

Produced in `output/`: `initial.data`, `final.restart`, `trajectory.dump`
(full per-atom id/type/x/y/z/vx/vy/vz), `thermo.csv`, `rdf.csv`,
`structure_stats.json`, `doctor_report.json`, `run.json`, plus the raw
`stage1/log.lammps` and `stage1/stdout.log`.

## resume

Rebuilds a continuation input from `output/final.restart` in a fresh
workspace, re-issuing the same `units`/`atom_style`/`pair_style`/`pair_coeff`/
`mass`/`timestep`/neighbor/`fix nve` lines so that velocities, box,
potential configuration and integration parameters are retained. Runs the
declared **50 debug steps** and emits `rdf_resume.csv`,
`thermo_resume.csv`, `structure_stats_resume.json`,
`trajectory_resume.dump`, `final_resume.restart`, `run_resume.json`.

## RDF / structure statistics

`rdf.csv` is computed **from the saved trajectory frames** in Python
(minimum-image pairwise distances, `g(r) = hist / (rho * N * shell_volume)`),
never from an analytic curve. `structure_stats.json` records atom count, box
lengths, density, first RDF peak position/height, coordination number of the
first shell, mean pair distance and the minimum-image MSD between the first
and last saved frame.

## GPU proof

`run.json` / `run_resume.json` contain `gpu_proof` and `device`. The task is
rejected (`status: gpu_backend_unproven` / rc=1) unless the LAMMPS execution
log mentions both `Kokkos` and `Cuda`/`GPU`.

## Honest limitations

* `input/manifest.json` currently declares `assets_ready: false` and
  `readiness.stage: design`. In this container `doctor` therefore reports the
  LAMMPS binary, the example script, the three Ta06A potential files and the
  `kokkos`/`cuda`/`snap`/`kk` capability tokens as missing and exits `78`.
  `run` and `resume` refuse to start and never claim success.
* Everything implemented here is the **debug** scale only
  (nrep=4, 100 + 50 steps). The reference-large instance
  (32x32x32 BCC cells, 65536 atoms, 50 ps = 100000 steps with a 5 ps
  continuation) is **not** executed and is not claimed.
* The 5 ps (10000 step) continuation is not performed at debug scale; the
  debug continuation is 50 steps as specified.
* No hyperparameter search, no ensemble averaging, no multi-GPU domain
  decomposition, no network access, no package installation.
* Timings and hashes are recorded from the actual execution; no synthetic
  numbers are written.
