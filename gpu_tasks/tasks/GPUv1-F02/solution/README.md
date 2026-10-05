# GPUv1-F02 (debug variant) — CAM5 All-Hist extreme-weather segmentation

Trains a small **3-level U-Net** (16 input channels → 3 classes, skip
connections, transposed-conv decoder) on the frozen debug slice of the
CAM5 All-Hist / TECA event-mask data and predicts per-pixel class masks for
the two official validation frames.

Classes: `0 background`, `1 tropical_cyclone`, `2 atmospheric_river`.

## Environment

* Single CUDA GPU (RTX 5090 in the stated test environment), PyTorch, NumPy.
* **CUDA is mandatory.** `train` and `predict` exit with code `3` if
  `torch.cuda.is_available()` is `False`. There is no CPU fallback and no
  surrogate/random model.
* No network access, no package installation, no host inspection.

## Commands

```bash
# 0) dependency / input audit (no training, no inference)
python solution/main.py doctor --input input
#    exit 0  -> everything needed is present
#    exit 78 -> report lists every missing file/dependency

# 1) required run
python solution/main.py train --input input --output output

# 2) reuse the checkpoint on new fields
python solution/main.py predict --checkpoint output/checkpoint.pt \
    --input path/to/new_fields.npy --output output/predict_new
```

`python solution/main.py --help` prints usage and never loads a model or
imports torch's model code.

### train flags (defaults are the single required configuration)

| flag | default | meaning |
| --- | --- | --- |
| `--seed` | 20240601 | python/numpy/torch/CUDA RNG seed |
| `--epochs` | 12 | epochs over all 6 training frames (72 updates) |
| `--lr` | 1e-3 | Adam learning rate |
| `--base` | 32 | U-Net base channel width |

## Inputs

`input/` must contain (shapes are checked):

| file | shape | dtype |
| --- | --- | --- |
| `train_fields.npy` | (6, 16, 192, 288) | float |
| `train_labels.npy` | (6, 192, 288) | int, values in {0,1,2} |
| `validation_fields.npy` | (2, 16, 192, 288) | float |
| `manifest.json` | — | input manifest |

The 192×288 fields are the native 768×1152 CAM5 domain decimated by the
frozen stride-4 sampling; channel semantics are preserved.

## Method (what actually happens)

1. Per-channel normalization: `mean`/`std` computed **from the training
   fields only**; stored in the checkpoint.
2. Class weights from the real training labels:
   `w_c = min((1/freq_c)^0.5, 30)`, normalized to mean 1.
3. Real gradient updates with `CrossEntropyLoss(weight=w)`: 12 epochs ×
   6 frames = **72 CUDA forward/backward/optimizer updates**, covering all
   six training fields every epoch.
4. Inference on the two validation frames → `predictions.npy` (argmax,
   values 0..2) and `probabilities.npy` (softmax).
5. Checkpoint is written, then **reloaded into a freshly constructed model**
   and re-run on a validation frame; the maximum absolute logit difference
   is recorded in `run.json` (`reload_check`).
6. Training IoU is computed against the real training labels and reported
   (`train_iou`) purely as a sanity signal.

## Outputs (`output/`)

| file | contents |
| --- | --- |
| `checkpoint.pt` | model state, optimizer state, `step`, normalization mean/std, class weights, seed, python/numpy/torch/CUDA RNG state, loss history, train IoU, config |
| `predictions.npy` | (2, 192, 288) int64, values 0..2 |
| `probabilities.npy` | (2, 3, 192, 288) float32 softmax probabilities |
| `run.json` | inputs, shapes, device, synchronized timings, config, loss history, IoU, reload check, prediction class counts |

`predict` writes `predictions.npy`, `probabilities.npy` and `predict.json`
into its own `--output` directory.

## Honest limitations

* This is the **debug** variant: a small 3-level U-Net, not the official
  DeepCAM/DeepLabV3+ reference, and 6 training / 2 validation frames, not
  the 4096/1024-frame reference-large protocol. No MLPerf-quality claim is
  made.
* The validation frames ship **without labels**; the headline per-class IoU
  is computed by the external oracle on private data. The `train_iou`
  reported here is optimistic (in-sample) and is *not* a quality claim.
* Labels are TECA-derived from a CAM5 simulation, not human observations.
* Event classes are extremely imbalanced; with a debug-sized budget the
  model may still under-predict rare classes. If
  `validation_all_background` is `true` in `run.json`, the run is honest
  about it rather than being presented as a success.
* Predictions are trained on 192×288 stride-4 fields only; `predict`
  expects inputs of the same grid and channel count.
