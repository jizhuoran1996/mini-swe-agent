# GPUv1-B04 — debug variant: reloadable road-scene segmenter

Source: `nvidia/segformer-b0-finetuned-cityscapes-1024-1024`
(revision `21b3847fae21ddee674abd31129307b6a1235bd9`) fine-tuned with real
CUDA gradients on the 24-image / 8-held-out debug split shipped in `input/`.
Labels are Cityscapes **trainID** PNGs, values `0..18`, `255 = ignore`.

## Commands

```bash
python solution/main.py --help
python solution/main.py doctor  --input input
python solution/main.py train   --input input --output output
python solution/main.py predict --checkpoint output/checkpoint \
                               --input input/validation.jsonl \
                               --output output/preds_reload.npy
```

The only required run is `train`. It performs one pass over the 24 training
records (`--epochs`, default 2) with `AdamW`, `CrossEntropyLoss(ignore_index=255)`,
and every training image produces at least one gradient update.

## Notes on preprocessing / postprocessing

* `AutoImageProcessor` is used with **`do_resize=False`**, so the 512x256 source
  image is not resized by the processor; the model's own strided encoder does the
  downsampling.
* Logits returned by the SegFormer decode head are bilinearly interpolated back
to the original image size before the loss / argmax, matching the required
"logits -> original resolution" behaviour.
* Output `predictions.npy` is `(8, 256, 512)` `int32` trainID maps for the eight
  held-out images listed in `input/validation.jsonl`.

## Outputs written by `train`

| path | contents |
|---|---|
| `output/checkpoint/` | HF `model.safetensors`/`config.json` + `preprocessor_config.json` |
| `output/training_state.pt` | optimizer state, `global_step`, epochs, torch/CUDA/NumPy/Python RNG states |
| `output/predictions.npy` | `(8, 256, 512)` `int32` label maps |
| `output/run.json` | config, real wall-clock timings, weight hashes, train-split mIoU |

`run.json` stores the SHA-256 hash of the model parameters before and after the
run and asserts `weights_changed == true`, i.e. a genuine update occurred.

## `doctor`

`doctor` never starts training or inference. It checks the two required jsonl
files, every referenced image / label file, the model snapshot files and the
`torch` (`cuda.is_available()`) / `transformers` dependencies, prints a JSON
report and exits with `78` if anything is missing, `0` otherwise.

## Known limitations (honest)

* This is the **debug** variant only: 24 train / 8 held-out images, SegFormer-B0,
  short schedule. The full Cityscapes `160k`-iteration MiT-B2 reference-large
  profile is *not* claimed and not reproduced here.
* `predictions.npy` is the deliverable pixel map; no PNG visualisation is
  written. Class-area summaries and full-val PNG export from the reference spec
  are out of scope for the debug variant.
* Held-out images ship without labels, so the reported `train_miou` is computed
  on the labelled training split as a sanity metric, not a validation score.
* CUDA is mandatory. `train`/`predict` fail fast when `torch.cuda.is_available()`
  is false; there is no CPU fallback and no synthetic/dummy weights.
