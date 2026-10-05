# GPUv1-F07 — FCN3 / ERA5 ensemble forecast adapter

Source-native adapter around the genuine **Earth2Studio FCN3** pretrained
checkpoint and **NCAR_ERA5** initial conditions.  Debug scope: one source
date, two members, two 6-hour steps, native 0.25° global grid.

## Entry points

```
python main.py --help
python main.py doctor --input input
python main.py run    --input input --output output
python main.py run    --input input --output output --resume
```

`--help` and the module import never load the model or touch CUDA.

### doctor

Prints a JSON report of

* presence of every file listed in `input/manifest.json`
  (`fcn3_checkpoint`, `era5_initial.nc`, `forecast_config.json`),
* importability of `torch numpy xarray netCDF4 earth2studio`,
* CUDA availability and device name.

Any missing item appears under `missing` and the process exits **78**.
Exit 0 means the environment and inputs are complete.

### run

The command first runs the same check as `doctor`.  If anything is missing
it prints `{"status": "missing_inputs", ...}` and returns **78** without
starting any GPU work — there is no CPU fallback and no synthetic data.

When the check passes it:

1. loads the genuine FCN3 checkpoint from `input/fcn3_checkpoint`,
2. reads `input/era5_initial.nc` and maps it onto the model's native
   coordinates (`model.input_coords()`),
3. iterates over members, seeding CPU/CUDA/numpy RNG per member, and calls
   the model for each 6-hour step (debug scope: 2 members × 2 steps),
4. writes `output/forecast.nc` (dims `member, lead, variable, lat, lon`),
   `output/ensemble_statistics/{mean,std}.nc`,
   `output/regions/hazard.json` — regional wind speed and t2m summaries
   computed **from the predictions**, not from climatology,
5. writes `output/verification/era5_scores.json` if
   `input/era5_validation.nc` is present,
6. saves the complete restart state in `output/forecast_checkpoint/state.npz`
   (full prognostic tensor for every member, native var/lat/lon coords,
   init time, `steps_done`, member IDs, torch-CPU / torch-CUDA / numpy RNG
   snapshots) plus `seed_weight_manifest.json` and `run.json`,
7. `torch.cuda.synchronize()` is called before each checkpoint write so the
   on-disk state reflects completed device work.

### resume

`run --resume` reloads `forecast_checkpoint/state.npz`, restores every
prognostic channel, every member's RNG state and the step index, then
advances exactly one additional 6-hour step per member.  Existing analysis
fields are read back from `forecast.nc` and appended to — no member is
duplicated and no seed is reset.

## Input contract

All paths and hashes are taken from `input/manifest.json`.  The adapter
never copies ERA5 truth as a prediction, never interpolates a
lower-resolution field onto the 0.25° grid, and never substitutes a CPU or
random model.

`input/forecast_config.json` is expected to carry at least:

```json
{"init_time": "2020-02-11T00:00:00", "members": 2, "steps": 2, "seed": 20240211}
```

## Honest limitations

* The container in which this adapter was authored did **not** have the
  FCN3 checkpoint, the ERA5 initial file or the Earth2Studio package
  mounted (`manifest.assets_ready == false`).  Consequently no run was
  executed here and no `output/run.json` could be produced.  `doctor`
  exits 78 for exactly this reason and no deliverable in this directory
  should be read as evidence of a completed forecast.
* The exact stochastic member-differentiation mechanism used by FCN3 (e.g.
  latent-noise injection) follows the upstream Earth2Studio `PrognosticModel`
  interface.  If the pinned Earth2Studio revision implements FCN3 as a fully
  deterministic model, member diversity must come from the per-member RNG
  seeded initial-condition perturbation that the config file enables; that
  switch is not exercised in this repository because the assets were absent.
* This is explicitly the **debug** scope.  A successful debug run does not
  constitute passing the reference-large configuration (4 initial dates ×
  32 members × 60 steps).
* Peak-memory and step timings recorded in `run.json` are genuine wall-clock
  and CUDA-allocator numbers from the actual run; they are not calibrated
  reference measurements.
