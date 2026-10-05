# GPUv1-B02 (debug): reloadable detection catalogue

## What it does

Builds a queryable object-detection catalogue for the 16 genuine COCO val2017
images listed in `input/images.json`. Detection is performed with the official
TorchVision **RetinaNet ResNet50-FPN** COCO checkpoint declared in
`/models/torchvision/retinanet.json` on CUDA. Parameters are frozen at
`min_size=320`, `max_size=640`, `score_threshold=0.25`. COCO category IDs are
kept verbatim. No retraining is performed.

This is the **debug variant** of task GPUv1-B02. It is not the OpenImages V6
`reference_large` workload.

## Usage

```bash
python solution/main.py doctor --input input
python solution/main.py detect --input input --output output
python solution/main.py query  --catalog output/catalog.json --image-id 139
python solution/main.py --help
```

`doctor` inspects all required files and dependencies and exits 78 if anything
is missing, 0 otherwise, without running any training or inference (it does
perform a strict checkpoint load check, no forward pass).

## Outputs (under `output/`)

* `detections.json` — one record per image
  (`image_id`, `file_name`, `original_size`, parallel `boxes`/`labels`/`scores`
  lists in COCO coordinates, sorted by descending score; zero-box images still
  appear).  Also carries model name, weights SHA-256, frozen parameters and
  category map.
* `catalog.json` — category map, image-to-index map, model/parameter binding.
* `run.json` — wall clock, per-image synchronized timing, device/version
  info, weights hash, `strict_load: true`, checkpoint wrapper used.

## Checkpoint binding — strict, no remapping

The declared checkpoint is loaded onto the exact declared architecture:

```python
retinanet_resnet50_fpn(weights=None, weights_backbone=None,
                       num_classes=91, min_size=320, max_size=640)
model.load_state_dict(state, strict=True)
```

Key properties:

* The checkpoint is fed to `load_state_dict` as **the original OrderedDict**.
  We never rebuild or re-key it, so the TorchVision RetinaNet head-version
  migration handled by `_load_from_state_dict` (which reads
  `OrderedDict._metadata`) takes effect exactly as on any official load.
* `strict=True`: any missing or unexpected key raises. There is no
  coverage-based acceptance, no shape-matched remapping of keys, and no
  silent retention of randomly-initialized head layers.
* Only well-known *container* wrappers (`model`, `state_dict`, ...) are tried,
  each with a fresh model instance, still preserving their `_metadata`.
* If no candidate loads strictly, `detect` and `doctor` fail with the full
  error report — they do not run with a partially-loaded model.

## CUDA requirement

Detection requires a usable CUDA device. `detect` exits non-zero if
`torch.cuda.is_available()` is False; `doctor` reports missing CUDA as a
missing item. No CPU fallbacks and no mock weights.

## Honest limitations

* Only the 16 COCO images listed in `input/images.json` are processed.
  This is a debug variant, not the full OpenImages V6 validation workload and
  not a `reference_large` run.
* No COCO mAP is computed here; the independent oracle computes it against
  frozen ground truth.
* Categories are the TorchVision COCO metadata list (91-slot indexing).
* Timings are single-forward synchronized measurements on whatever GPU is
  available; no throughput claims.
* Output labels are model predictions, not source annotations.
