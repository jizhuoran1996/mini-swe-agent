# GPUv1-F09 - Source-native PhysicsNeMo AeroGraphNet adapter (DrivAerNet v1)

Source-native adapter that orchestrates the upstream PhysicsNeMo **AeroGraphNet**
`+experiment=drivaernet/agn` training pipeline against real **DrivAerNet v1**
surface meshes and matching CFD surface-field labels (pressure, wall shear), and
emits surface field `.vtp` files plus a drag prediction table.

The task's own `input/manifest.json` declares `assets_ready: false`. That means
on this host the required native inputs and framework modules are **not**
mounted, and the honest behaviour of this adapter is to refuse the run with exit
code `78` and a machine-readable list of missing assets, rather than fabricate
inputs, generate synthetic CFD labels, or fall back to CPU.

## Entry points

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output
python solution/main.py resume --input input --output output
```

* `--help` never imports `torch`/`physicsnemo`/`dgl`/`pyvista` and works with no
  framework present.
* `doctor` inspects the exact required files listed in `input/manifest.json`
  (`upstream/physicsnemo/examples/cfd/aerographnet/train.py`,
  `drivaernet/train_manifest.json`, `drivaernet/validation_manifest.json`,
  `drivaernet/geometry_and_fields`) plus the required modules
  (`physicsnemo`, `dgl`, `pyvista` + `torch`). It also probes CUDA. It writes a
  JSON report and exits `78` if any file or module is missing, `0` otherwise.
* `run` runs the same gates in order (inputs -> modules -> CUDA) and refuses to
  spawn the upstream job if any gate fails. Only when all three gates pass does
  it invoke the upstream `train.py` with the frozen
  `+experiment=drivaernet/agn` Hydra config, i.e. native graph construction,
  native message passing, native loss, and native checkpointing (model +
  optimizer + RNG + normalization stats).
* `resume` checks for a saved checkpoint directory and then re-invokes the same
  native upstream path, letting the drivaernet/agn config reload state. If no
  state exists it reports `NO_RESUMABLE_STATE` with exit `78`.

## What is real vs. what is blocked on this host

* The adapter does **not** download, generate, or substitute any mesh, field or
  drag label. `input/manifest.json` -> `assets_ready: false`, so on this host
  every real run returns exit `78` with `status": "BLOCKED_MISSING_INPUT_ASSETS"`.
* No synthetic pretrained weights or random-initialised stand-in model is used.
  The only weights that can be trained / reloaded here are the ones produced by
  the upstream PhysicsNeMo AeroGraphNet `drivaernet/agn` config on the admitted
  DrivAerNet v1 data.
* No CPU fallback: if `torch.cuda.is_available()` is false, `run` exits `1`.

## Outputs (when the native path is admitted)

Written under `--output`:

* `checkpoints/`  - reloadable AeroGraphNet checkpoint(s) with optimizer, RNG
  and normalisation statistics, so `resume` is meaningful.
* `predicted_fields/*.vtp` - per-vehicle surface-field predictions of pressure
  and wall shear on the original mesh nodes of the official held-out split.
* `drag_predictions.csv` - drag coefficient per vehicle plus held-out
  pressure / wall-shear / drag error metrics.
* `run.json` - mode, command, stages, per-stage wall time, CUDA/device info,
  exit status and a list of produced artefacts. Also written when a gate fails,
  so the failure reason is recorded on disk.

## Honest limitations

* The `scale_plan.debug` workload ("fixed 2 training / 2 validation vehicles,
  original grid preprocessing, build-only check") is **not** a substitute for
  the `reference_large` full DrivAerNet v1 train/val/test run, and this adapter
  never reports the debug path as if it were the reference scale.
* The `reference_large` configuration (full v1 splits and the reference update
  budget) cannot be executed on this host because the native assets and GPU
  frameworks are not admitted.
* No Ahmes / DrivAerNet++ samples are mixed in; all manifests must come from
  the frozen DrivAerNet v1 revision declared by `input/manifest.json`.
* Independently verifying drag curvature, no-leak splits and unit
  normalisation is the job of the task's evaluator; this adapter only produces
  the artefacts.
