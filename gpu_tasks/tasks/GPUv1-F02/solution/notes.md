# Notes

* `main.py --help` and `doctor` never import torch's model code or build a
  network — `_model_classes()` is lazy.
* `doctor` returns 0 only when all four required files exist with the
  expected shapes, the manifest parses, the declared sha256 digests match,
  torch/numpy import, and CUDA is available. Otherwise it returns 78 and
  prints a `missing` list.
* `doctor` reads `.npy` files with `mmap_mode='r'` so nothing but headers
  is touched.
* `train` refuses to run without CUDA (exit 3), refuses to run without the
  three arrays (exit 2), and fails loudly if fewer than 5 updates happen,
  if the loop does not cover all 6 training fields, or if the checkpoint
  reload does not reproduce identical logits (exit 5).
* No hyperparameter search, no ensembles, no repeated-sample padding: the
  one required configuration is run once.
