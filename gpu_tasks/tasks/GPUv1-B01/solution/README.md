# GPUv1-B01 (debug variant) — ResNet-50 fine-tune on a real CIFAR-10 subset

## What this is

Fine-tunes an **official TorchVision ResNet-50** initialised from real ImageNet
pretrained weights (`/models/torchvision/resnet50.json`) on a **real CIFAR-10
subset**: 1000 uint8 NHWC `32x32x3` training images and 100 validation images.
Images are bilinearly resized to 224x224 and normalised with the ImageNet
mean/std. The 1000-class `fc` is replaced by a fresh `Linear(2048, 10)` which is
the only trainable module (the backbone is frozen to fit the debug budget).
Training is a genuine CUDA forward + backward + Adam update loop.

## Usage

```bash
# 0) environment / input inspection (no training, no model loading)
python solution/main.py doctor --input input          # exit 0 ok, 78 missing

# 1) train
python solution/main.py train --input input --output output

# 2) reload the checkpoint and predict on new images
python solution/main.py predict --checkpoint output/checkpoint.pt \
    --input new_images.npy --output new_predictions.npy

python solution/main.py --help                        # never imports torch
```

## Outputs written to `output/`

| file | content |
|---|---|
| `checkpoint.pt` | full `state_dict` (frozen backbone + trained head), Adam `optimizer_state_dict`, `step`, `epochs`, seed, preprocessing constants, torch/CUDA/NumPy/Python RNG states, the list of train indices actually used, and the pretrained-init provenance |
| `validation_predictions.npy` | float32 `(100, 10)` softmax over the validation split, produced by a second forward pass of the trained model on CUDA |
| `run.json` | config, device/torch/CUDA versions, synchronized wall-clock timings, loss trace, head-update magnitudes, coverage report |

## Determinism and state

Seed `1234` by default (`--seed`). `torch.manual_seed`, `torch.cuda.manual_seed_all`,
`numpy.random.seed` and `random.seed` are set before the model is built, and the
batched forward/backward pass uses a dedicated `torch.Generator` so the sample
order is reproducible. All four RNG states are stored in the checkpoint.

## Coverage guarantee

Every epoch shuffles all 1000 training indices, so after the first full epoch
every image has contributed to at least one gradient update. The exact set of
indices that were touched is recorded in both `checkpoint.pt`
(`train_indices_seen`) and `run.json` (`coverage.all_train_images_used`).

## Honest limitations

* **This is the debug variant.** It is *not* a completed ImageNet-1K training
  run and it makes no reference-large claim. The data is CIFAR-10, not ILSVRC2012.
* **Validation accuracy is not computed or reported here.** Only the images are
  provided (`validation_images.npy`); the labels are held by the independent
evaluator. `validation_predictions.npy` contains probabilities only.
* The backbone is frozen — only the 10-class head receives gradients. This is an
  explicitly allowed debug-budget choice, not the reference 90-epoch recipe.
* Requirements: a CUDA device (checked and hard-failed otherwise), PyTorch and
  TorchVision importable, and a locally resolvable pretrained ResNet-50
  checkpoint. If no pretrained weights can be found locally, `train` refuses to
  run rather than training from random initialisation.
* No data augmentation, no AMP, no multi-GPU/NCCL path, no hyperparameter search
  and no ensembling are used — one deterministic run per invocation.
