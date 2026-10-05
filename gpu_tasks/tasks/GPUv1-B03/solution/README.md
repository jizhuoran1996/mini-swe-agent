# GPUv1-B03 (debug variant) - Mask R-CNN instance segmentation & contour export

## What this does

Trains the standard TorchVision `maskrcnn_resnet50_fpn` (ResNet50-FPN) on the
12 real COCO images that carry instance segmentation annotations
(`input/train_annotations.json`), then runs inference on all 16 images and
exports:

* `checkpoint.pt` - full standard TorchVision `state_dict` plus model config,
  optimizer state, step count, and Torch/CUDA/NumPy/Python RNG state.
* `instances.json` - per-image predicted boxes / labels (COCO 91-ID) / scores
  and per-instance COCO RLE masks (`pycocotools` encoding).
* `contours.json` - outer boundary polygons of the binary prediction masks,
  in original image pixel coordinates.
* `run.json` - real, synchronized timings, losses, device info.

## Usage

```
python solution/main.py train   --input input --output output
python solution/main.py predict --checkpoint output/checkpoint.pt \
                                --input input --output output/reloaded
python solution/main.py doctor  --input input
```

`doctor` inspects the required files (`train_annotations.json`, `images.json`,
`images/`, the weights spec `/models/torchvision/maskrcnn.json`) and the runtime
environment (CUDA, torch, torchvision, pycocotools, numpy, Pillow, and a contour
backend).  It also tries to resolve the weights spec (without building the model)
and prints how it was resolved.  It exits **0** when everything is present,
**78** (`EX_CONFIG`) when any item is missing, and it never runs training or
inference.

`main.py --help` prints help without importing torch.

## Weights resolution

The spec file `/models/torchvision/maskrcnn.json` is a free-form JSON.  The
loader walks every string in the file and tries, in order:

1. Local file path (as-is, relative to the spec directory, to its parent, or to
   the current directory).  A loaded `torch.load(..., weights_only=False)`
   object is unwrapped through the common `model` / `state_dict` /
   `model_state_dict` / `weights` / `params` keys and a `module.` DataParallel
   prefix is stripped.  The number of classes is inferred from
   `roi_heads.box_predictor.cls_score.*`.
2. The string interpreted as a TorchVision **enum member** name, e.g.
   `COCO_V1`, `DEFAULT`, or a dotted
   `MaskRCNN_ResNet50_FPN_Weights.COCO_V1`; also tried against
   `ResNet50_Weights` for an ImageNet backbone.
3. A stem + common extension (`.pth/.pt/.pkl/.bin/.ckpt/.tar`) next to the spec
   or its parent.
4. Heuristics on keys like `coco`, `maskrcnn`, `imagenet`, `r-50`.
5. Any solitary weight file in the spec directory, its parent, or the usual
   Torch Hub cache directories.

If nothing resolves, the command exits **78** and prints the spec contents so
that the operator can see exactly what was rejected.  It never silently falls
back to random weights.

## Training

* Config: `min_size=320`, `max_size=640`, COCO **91-ID** class convention
  (background index 0, categories 1..90 == torchvision's COCO label space).
* One optimizer update per annotated image (batch size 1, SGD, lr 1e-4).
  Each image is decoded through `pycocotools.COO.annToMask`, so real polygon /
  RLE instance masks (not boxes) drive the mask head and loss.
* Real gradient check: after every `backward()` we assert `sum(|grad|) > 0`
  on the model parameters, and `loss_mask` must be present in the loss dict.
* After the loop we assert at least one parameter tensor actually changed
  before/after training, then reload `checkpoint.pt` through the same
  construction path and compare every tensor for byte equality.

## Prediction

* Score threshold 0.25 (boxes/labels/scores), mask threshold 0.5.
* Predicted masks (already resized by torchvision's `paste_masks_in_image` to the
  original image dimensions) are encoded with `pycocotools.mask.encode` into
  `[size=[H, W], counts=...]` RLE; area/bbox come from the RLE.
* Contours are extracted from the binarised mask (outer boundary only) using
  OpenCV if present, falling back to `skimage.measure.find_contours`, then to a
  bounding-box polygon.  Coordinates are in original image pixels.

## Honest limitations

* This is the **debug** variant: 12 labelled images and 4 image-only files, a
  single SGD pass, no hyperparameter search, no ensembling.  It is a smoke run
  that proves the end-to-end pipeline (data -> train -> reload -> predict ->
  RLE -> contours -> report) works with real CUDA mask loss and real gradient
  updates.  It is **not** a trained COCO model and cannot reach the reference
  Mask R-CNN quality; only pipeline correctness and consistency are claimed.
* The `reference-large` specification (`instances_train2017.json`,
  `instances_val2017.json`, 270k iterations, 4-8 GPU data parallel) is not
  attempted here and is not claimed.
* If neither `/models/torchvision/maskrcnn.json` nor the local Torch Hub cache
  resolves a state dict or a TorchVision weights enum, the command exits 78
  rather than silently initialising random weights.
* Prediction is thresholded; objects with score <= 0.25 are not exported.
* Contour fidelity depends on the available contour backend; the fallback
  bounding-box polygon is only used when OpenCV and scikit-image are both
  absent (unlikely in the stated environment).
