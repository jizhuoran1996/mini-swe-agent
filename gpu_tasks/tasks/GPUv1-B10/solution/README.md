# GPUv1-B10 (debug variant) - outdoor metric monocular depth adaptation

Adapts `depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf` (revision
`fd2c22027eaf20374204f14099b8341e1925ad39`, local copy at
`/models/depth-anything--Depth-Anything-V2-Metric-Outdoor-Small-hf`) on the
packaged VKITTI2 debug split: 12 train RGB + metric depth frames, 4 held-out
frames, 392x126. Real CUDA gradient updates, real HF checkpoint export.

## Commands

```bash
python solution/main.py --help
python solution/main.py doctor  --input input --output output
python solution/main.py train   --input input --output output
python solution/main.py predict --checkpoint output/checkpoint \
                                --input input/validation.jsonl \
                                --output output/predictions.npy
```

Exit codes: `0` success, `78` (EX_CONFIG) missing inputs/assets/checkpoint,
`1` runtime failure (including "CUDA not available").

## What `train` does

1. Parses `input/train.jsonl` / `input/validation.jsonl` and resolves image and
   depth paths (absolute, or relative to the jsonl / input dir).
2. Refuses to start GPU work when any declared train image or depth file is
   absent.
3. `AutoImageProcessor` + `AutoModelForDepthEstimation.from_pretrained` from the
   local model dir; the model runs in float32 on `cuda:0`.
4. Loss = `mean(|predicted_depth - target_depth|)` restricted to valid pixels,
   valid = `finite & 0.1 m < depth < 80 m` (outdoor range, mask from the label).
   `predicted_depth` is bilinearly interpolated to the native depth/GT size
   before the loss, exactly as required.
5. At least 12 optimizer updates; with `--epochs 1` every train frame enters
   exactly once (one frame per update, batch size 1). Gradients are checked for
   finiteness before each `optimizer.step()`; weights are checked after.
6. Held-out inference with `model.eval()` produces `output/predictions.npy`
   `(4, 126, 392)` float32 metres plus coverage statistics.
7. Writes `output/checkpoint/` (`save_pretrained` + processor, reloadable by a
   fresh process), `output/train_state.pt` (AdamW state, step, loss/grad
   history, Python/NumPy/torch-CPU/torch-CUDA RNG states), `output/run.json`
   (config, synchronized wall timings, per-step losses, weight-norm delta,
   coverage, metrics) and `output/predictions_meta.json`.

AdamW, lr `1e-5` (override with `--lr`), seed `0` (`--seed`). `--freeze-backbone`
freezes `model.backbone` and trains only the DPT depth head. No AMP, no
accumulation, no hyperparameter search, one run.

## What `predict` does

Fresh process, loads `--checkpoint` with the HF API, requires CUDA, resolves the
image paths in the given jsonl, predicts metric depth, bilinearly resizes to the
native image/depth size and saves a float32 metres `.npy` plus a sidecar JSON.

## Metrics and limits (honest)

- `AbsRel` and `RMSE` are reported in `run.json`/`predict` sidecar **only if the
  held-out records carry local depth labels**. When the held-out labels are
  hidden, the fields stay `null` with `"source": "hidden (no local labels
  supplied)"` - the code never fabricates them and never uses validation labels
  for training or per-image rescaling.
- `coverage` = fraction of output pixels that are finite and inside
  `(0.1 m, 80 m)`; it is reported per image.
- Depth normalisation: the manifest declares VKITTI2 native uint16 centimetres;
  integer arrays are divided by 100. Float arrays are treated as metres unless
  their finite maximum is clearly centimetre-scaled (> 200), in which case they
  are divided by 100 as well. This is a heuristic and is documented, not hidden.
- This is the **debug** variant only (`scale = debug_only`,
  `formal_large_tested = false`). It does **not** reproduce the reference-large
  ViT-L, 518-crop, 40-epoch, full-split run, and it does not export point clouds
  (no camera intrinsics are shipped with this debug manifest).
- Requires a real CUDA device; there is no CPU fallback by design.
- No network access, no package installation, no shelling out, no host probing;
  inputs are read-only and only `solution/` and `output/` are written.

## Data licence

VKITTI2 is CC BY-NC-SA 3.0 (non-commercial). The model is adapted from synthetic
VKITTI2 frames; no KITTI ground-truth labels are used for training.
