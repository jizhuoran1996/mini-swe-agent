# GPUv1-C06 - ProPainter masked-region completion (debug variant)

Restores the regions marked white in `input/masks/*.png` of the 16 real VKITTI2
frames in `input/frames/*.png` using the **official** `sczhou/ProPainter`
inference script (`input/upstream`) and the **official** pretrained weights
(`/models/ProPainter`). The clean reference frames are never read.

## Usage

```bash
python solution/main.py --help                    # no model loading
python solution/main.py doctor --input input      # 0 = available, 78 = missing
python solution/main.py run --input input --output output
```

`--input` may point at any directory that contains `frames/`, `masks/` and
`upstream/`, so a new run can process another frame/mask directory.

## What `run` does

1. `doctor` gate: required input files, official source files and official
   weights must all be present and `torch.cuda.is_available()` must be `True`
   (otherwise exit 78 / 2).
2. Copies the official source tree into `output/_propainter_work/propainter_src`
   and symlinks the three official weights into `<run>/weights/` so the
   upstream auto-download path is never taken.
3. Stages frames and masks at 320x192.
4. **Child-environment probe.** The official script's whole dependency graph is
   imported (never executed) in a fresh interpreter whose CWD is the official
   source root and whose `PYTHONPATH` is *prepended* with that same root. The run
   is refused with exit 78 before spawning the job if that import fails.
5. Runs the official script with `--video ... --mask ... --output ...
   --width 320 --height 192 --fp16 --neighbor_length 10 --ref_stride 10
   --subvideo_length 16 --save_frames`. The optional flag list is validated
   against the source's own `inference_propainter.py --help` and only emitted
   when supported; the three mandatory flags are always passed.
6. Composites the network output with the input: protected pixels (mask == 0)
   are copied back byte-for-byte from the input frame, masked pixels come from
   the model. Every frame is processed by the model; no frame is skipped and no
   frame is copied from a neighbour.
7. Writes `output/frames/<index>.png`, `output/repaired.mp4`,
   `output/frame_manifest.json` and `output/run.json` (configuration, weight
   hashes, exact command, real timings, GPU info, peak VRAM, probe results and
   structural checks).

## Fix vs. the previous revision

The **optional** masked-region temporal-consistency statistic used to compare
`comp[mm]` (shape `(N, 3)` after boolean indexing with the *current* frame's
mask) against the previous step's full-frame buffer `prev_masked` (shape
`(H, W, 3)`), which crashed with a NumPy broadcasting error once the official
inference succeeded and the loop reached the metric.

The metric is now computed by the helper `_temporal_masked_mae(...)`, which
keeps the previous **full** repaired frame and indexes **both** operands with
the **same** mask (the current frame's mask, further intersected with the
previous frame's mask). Both sides are then `(N, 3)` `float32` and no
broadcasting between different shapes can occur. The computation is wrapped in
try/except and only appends a warning on failure, so this optional statistic
can never take down the mandatory deliverables (`frames/*.png`,
`repaired.mp4`, `frame_manifest.json`, `run.json`).

Additionally, the doctor probe now runs with the official source root as CWD
and prepended on `PYTHONPATH`, and the former inert `matplotlib` stub has been
removed.

## Honest limitations

* This is the **debug** variant (16 frames, 320x192). It is not the
  reference-large DAVIS run and does not claim to be.
* Masked-region PSNR/SSIM cannot be computed here because the clean reference is
  held privately by the verifier; `run.json` records those fields as `null` with
  a note and instead reports a masked-region temporal-consistency MAE.
* Video is encoded with OpenCV `mp4v` (no network, no extra codecs).
* The `--help`-based flag validation is a heuristic: it only prevents emitting
  flags the installed source does not know; the mandatory flags are always
  passed.
* `output/_propainter_work` keeps the copied source, staged inputs, inference
  log and the official script's raw output for auditability.
