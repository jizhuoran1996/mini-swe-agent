# GPUv1-F01 (debug variant) — CUDA 3D-CNN cosmological parameter regressor

Train a 3D convolutional regressor that maps a 128x128x128x4 density volume
(real CosmoFlow TFv2 `cosmoUniverse_2019_05_4parE_tf_v2_mini` crops) to four
normalised cosmological parameters, then reload the checkpoint and predict on
new volumes.

## Files

- `solution/main.py` — single-file implementation (CLI, model, training, prediction).
- `output/checkpoint.pt` — model config + weights + optimizer state + step + RNG states.
- `output/validation_predictions.npy` — `(2, 4)` float32 predictions for the two
  source validation volumes.
- `output/validation_predictions.csv` — same predictions, human readable.
- `output/run.json` — full run record (inputs/hashes, config, metrics, timings, memory).
- `output/metrics.json` — compact metrics + input hashes for downstream checkers.

## Usage

```bash
python solution/main.py --help
python solution/main.py doctor  --input input
python solution/main.py train   --input input --output output
python solution/main.py predict --checkpoint output/checkpoint.pt \
                                --input input/validation_fields.npy \
                                --output /tmp/val_preds.npy
```

`--help` only parses arguments; torch/numpy are imported lazily inside the
subcommands, so no model or CUDA context is created for help.

`doctor` reads only file headers and the environment: it lists every missing
required file (plus hash mismatches against `manifest.json`, unreadable npy
headers, shape problems and an unavailable CUDA device) and exits `78` if
anything is missing, `0` otherwise. It never trains or runs inference.

`train` writes `checkpoint.pt`, `validation_predictions.npy`,
`validation_predictions.csv`, `run.json` and `metrics.json`. `predict` loads a
checkpoint and writes a `(N, 4)` float32 `.npy` for arbitrary new volume
stacks.

## Method

1. Preprocessing (self-contained per volume, identical in train and predict):
   `x = log1p(max(count, 0))`, then `x = x / mean(x)` where the mean is taken
   per sample over all voxels and all four redshift channels; the divisor is
   `1.0` when that mean is 0.
2. Model: five strided 3D blocks `Conv3d(k=3, s=2, p=1, bias=False) +
   BatchNorm3d + ReLU` with channel widths `[w, 2w, 2w, 4w, 4w]` (`w=16` by
   default), then `AdaptiveAvgPool3d(1)` and a `Linear(4w, 4)` head. All four
   redshift channels are consumed by the first convolution.
3. Loss: MSE against the provided normalised source labels; Adam; every
   optimizer step is a real CUDA forward/backward/step. All training samples
   are visited each epoch (a full permutation), and the run is extended until
   at least 5 optimizer updates have happened.
4. Output clamping: if every source target lies in `[-1, 1]`, the head uses
   `tanh`, so each parameter is restricted to `[-1, 1]`. Otherwise the head is
   linear and the run record explicitly states that outputs are **not**
   clamped (`config.output_clamped_to_unit_interval = false`).
5. Timings use `torch.cuda.Event` plus `torch.cuda.synchronize()`, so the
   reported GPU seconds are real synchronised device time.

## cuDNN compatibility handling

Some container images ship a system `libcudnn` whose runtime version does not
match the version the PyTorch wheel was compiled against. In such images
`torch.backends.cudnn.version()` raises `RuntimeError: cuDNN version
incompatibility`. `main.py` never lets that abort the run: `doctor`, `train`
and `predict` probe cuDNN defensively and, if the probe fails, set
`torch.backends.cudnn.enabled = False` so that generic CUDA kernels are used
for the 3D convolutions. All computation still happens on the CUDA device
(`torch.cuda.is_available()` must be `True`), no CPU fallback is used, and the
fact that cuDNN was disabled is recorded as `cudnn_disabled: true` in
`run.json` / `metrics.json` / the `predict` output.

## Honest limitations

- This is the **debug** variant: 4 training volumes and 2 unlabelled validation
  volumes from the official mini TFRecord shards. It is **not** the
  reference-large MLPerf/CosmoFlow workload and makes no MLPerf claim.
- The model is a small PyTorch 3D CNN, not the official distributed
  TensorFlow/Horovod CosmoFlow network; no convergence or MAE threshold is claimed.
- The two validation volumes ship **without labels**, so no validation MSE/MAE
  can be computed here. `run.json` reports training-set MSE/MAE only, and this
  is stated explicitly (`validation_labels_available: false`).
- Targets are used in the provided normalised units; no de-normalisation
  constants are part of this bundle, so predictions are returned in the same
  normalised space as `train_targets.npy`.
- BatchNorm uses batch statistics during training and running statistics at
  inference time; predictions on very small batches may differ slightly from a
  full-batch reference.
- A CUDA device is mandatory: both `train` and `predict` fail fast with a
  non-zero exit code when `torch.cuda.is_available()` is false. There is no CPU
  fallback and no mock/pretrained weight substitution anywhere.
