# GPUv1-F08 - Source-native CorrDiff Taiwan downscaling adapter

This directory holds the operator interface requested by `TASK.md` and
`input/manifest.json` for the CorrDiff Taiwan downscaling task.

## Entry points

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output
python solution/main.py resume --output output [--members N] [--num-hours N]
python solution/main.py resume --output output --reextract
```

`--help` is instant: it never imports `torch`, `physicsnemo`, `zarr`,
`xarray` or `hydra`.

## doctor

`doctor --input input` performs a purely structural inspection and exits 78
when anything is missing. It checks:

* every entry of `manifest.json`'s `required_files` (`corrdiff/regression.mdlus`,
  `corrdiff/diffusion.mdlus`, `corrdiff_config.yaml`, `cwa.zarr`) including
  a valid zarr root (`.zgroup` / `zarr.json`);
* the `required_modules` (`physicsnemo`, `zarr`, `xarray`, `hydra`, `torch`, `numpy`);
* CUDA availability (with device name, total memory, and capability).

It never loads, evaluates, or downloads a model. It also computes SHA256 for
the declared files so the run manifest is reproducible.

## run

`run --input input --output output` is the real GPU job:

1. Fails immediately with exit 3 if CUDA is not visible to PyTorch.
2. Fails with exit 78 if any required input asset or Python module is missing
   (per the manifest) - the upstream job is never spawned from missing inputs.
3. Loads `corrdiff_config.yaml` with `omegaconf` (via PhysicsNeMo / hydra).
4. Loads `corrdiff/regression.mdlus` and `corrdiff/diffusion.mdlus` through
   `physicsnemo.Module.from_checkpoint` (falling back to `modulus.Module`).
5. Instantiates the source-native `physicsnemo.diffusion.CorrDiff` object and
   runs the real regression model plus conditional diffusion sampling on the
   native CWA coarse-resolution grid.  Every member uses its own deterministic
   seed (`base_seed + hour_index*1000 + member`).
6. Rejects absent predictor variables and unknown CorrDiff constructor
   signatures with a diagnostic error - no fabricated conditioning is used.

Files written under `output/`:

| Artifact                          | Meaning                                         |
|-----------------------------------|-------------------------------------------------|
| `ensembles/<YYYYMMDDTHH>/ensemble.npz` | Member ensemble for one hour (`[M, C, H, W]`). |
| `ensembles/<YYYYMMDDTHH>/mean.npy`    | Ensemble mean.                              |
| `ensembles/<YYYYMMDDTHH>/quantiles.zarr` | p10/p25/p50/p75/p90 with native coordinates. |
| `ensembles/<YYYYMMDDTHH>/lowres.npy`  | Coarse-resolution conditioning slice.       |
| `ensembles/<YYYYMMDDTHH>/stations.json` | Wind/precip summary at Taipei, Taichung, Kaohsiung, Hualien, Tainan. |
| `coverage.json`                   | Per-hour status (`complete` / `missing_in_source`) - missing hours are listed, never silently dropped. |
| `state.json`                      | Model paths, seed, member count, completed hours - the resume anchor. |
| `run.json`                        | Wall times, per-hour timings, CUDA device, seeds, members. |

## resume

`resume --output output` re-opens `output/state.json`, reloads the same
checkpoints, and:

* appends conditional-diffusion ensembles for hours not yet produced, or
* with `--next-hour`, generates one specific new hour, or
* with `--reextract`, recomputes station/quantile summaries from the stored
  ensembles only (no GPU sampling, no model reload needed beyond the zarr).

## Status on this host

`input/manifest.json` declares `assets_ready: false` and the gate states the
native datasets/checkpoints were not mounted.  On this container, `doctor`
lists the missing files/modules/CUDA and exits 78.  `run` and `resume`
refuse to proceed with the same exit code.  **No fabricated inputs, mocked
weights, CPU fallbacks, ERA5 upsamples, or copies of the mean substituted
for diffusion members are used anywhere in this implementation.**

## Honest limitations

* `run` targets the public `physicsnemo.diffusion.CorrDiff` API.  If the
  mounted PhysicsNeMo release exposes a different constructor (e.g. only
  `EDMPrecond` + an explicit EDM sampler loop), `_build_corrdiff` raises a
  clear RuntimeError instead of silently substituting a non-CorrDiff model.
* Reference scale (168 hours x 64 members) is out of scope for this debug
  container; the entry point accepts arbitrary hour/member counts so the
  same code path drives the full reference run once assets are admitted.
* The station list is the fixed Taiwan set required by the task brief; no
  additional site interpolation or gridding is performed.
