# GPUv1-B05 — volumetric kidney/tumor segmentation (source-native adapter)

Source-native adapter for the **MLPerf Inference KiTS19 reference 3D U-Net**
PyTorch CUDA workload (task `GPUv1-B05`, backend
`MLPerf KiTS19 reference 3D U-Net inference`).

The adapter **does not** reimplement the network. It loads the frozen reference
TorchScript checkpoint (`reference_model.pt`) and the officially preprocessed
volumes (`preprocessed/case_XXXXX.npy`) that the manifest declares, and performs
true 3D sliding-window inference over complete CT volumes on the GPU.

## Entry points

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output
python solution/main.py resume --input input --output output
```

- `doctor` inspects the input tree and dependency availability **without loading
the model**. It prints an env/info JSON block, lists every missing file/module/
capability, and exits `78` if anything is missing, `0` if all is present.
- `run` requires a ready input tree. It performs the actual GPU job for every
  declared case and writes the deliverables under `output/`.
- `resume` is `run --resume`: previously completed cases (tracked in
  `output/progress.json` with their mask SHA256) are skipped; the same reference
  model is reloaded for any new case.

If the input assets are absent (as declared by `input/manifest.json`:
`assets_ready: false`), `run`/`resume` refuse to proceed and exit `78`. No fake
inputs, random weights, downloaded models or CPU substitutes are used.

## What the adapter does

1. Reads `input/manifest.json`, `input/cases.json` and `input/reference_model.pt`
   as the sole source of truth for case IDs and case geometry.
2. Loads the reference TorchScript checkpoint with `torch.jit.load` and moves it
   to `cuda:0` in `eval()` mode (fp32; no silent precision change).
3. Loads each case's officially preprocessed `.npy` volume as a float32 3-D
   tensor (channel-first, channel-last, and multi-channel variants handled).
4. Runs a fully-3D sliding window inference: `128^3` patches, `0.5` overlap,
   overlap-add normalized by per-voxel coverage, then `argmax` to 3 classes.
   Whole volumes are processed; no single-slice or center-crop shortcuts.
5. Restores the mask to the case-declared shape when `cases.json` provides it,
   otherwise keeps the source preprocessed shape.
6. Writes per-case masks and sidecar affine/spacing, a volume CSV, a coverage
   manifest, resume state and a `run.json`.

## Deliverables

- `output/masks/case_XXXXX.npy` — uint8 volume, labels `{0:background, 1:kidney, 2:tumor}`.
- `output/masks/case_XXXXX.json` — sidecar: shape, dtype, classes, `spacing_mm`,
  `affine`, source preprocessed file, model SHA256, mask SHA256, patch/overlap.
- `output/volumes.csv` — per-case voxel counts and mL volumes for kidney and tumor
  recomputed from real voxels × real spacing.
- `output/manifest.json` — case coverage, per-case mask paths and hashes.
- `output/progress.json` — resumable state keyed by case id.
- `output/run.json` — task id, backend, config, device name, input hashes,
  timings, coverage, output paths, notes.

## Environment / limitations (honest)

- Requires **CUDA**. The task fails (`exit 78`) if `torch.cuda.is_available()` is
  false. There is no CPU fallback.
- Requires `torch` and `numpy`. `nibabel` is **not** assumed; deliverables use
  explicit `.npy` volumes plus a JSON `affine`/`spacing_mm` sidecar as allowed by
  “明确声明的体素数组及 affine/spacing sidecar”.
- The exact `cases.json` schema is source-defined. The extractor handles lists of
  records, `{cases:[...]}` wrappers, dict-keyed records and direct id scalars,
  and pulls `spacing`/`original_shape`/`affine` when present (falling back to
  1 mm isotropic and the preprocessed shape).
- This is a **debug vs. reference-large** split. The declared debug scope is
  “2 real source cases, full volume”. Passing the debug run does **not**
  constitute reference-large/full 42-case acceptance. `reference_large_tested`
  is reported as false unless a full 42-case run is actually executed.
- Downstream re-check (Dice against oracle labels, slice/CC summaries) is
  expected to be performed against these delivered voxel arrays and sidecars by
  an independent tool, not by this adapter.
