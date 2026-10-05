# GPUv1-B09 -- OSTrack ViT-Base single-object tracker on GOT-10k

Source-native adapter around the official OSTrack training and testing
entry points, using the official GOT-10k config
`vitb_384_mae_ce_32x4_got10k_ep100` and the MAE ViT-Base public source
weights.

## Entry points

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output \
    [--epochs 1] [--train-seqs 4] [--val-seqs 4]
python solution/main.py resume --input input --output output
```

`--help` never imports torch / timm / cv2 and never loads a model.

## Doctor

`doctor` reads `input/manifest.json`, then verifies every listed file
(sha256 is computed for files up to 256 MiB) and every listed python
module (`timm`, `cv2`, `yaml`, `lmdb`).  It prints a JSON report.

* Everything present -> exit `0`.
* Any file or module missing -> exit `78`, and the `run` / `resume`
  sub-commands refuse to spawn any upstream job.

## Run

1. `require_cuda()` -- abort with a hard error if `torch.cuda` is not
   available.  No CPU fallback is ever used.
2. `build_mirror()` creates `output/GOT10k/{train,val}/list.txt` containing
   a fixed small subset of the real GOT-10k lists (debug scope), and
   symlinks only those sequence directories.  The input tree stays
   read-only.
3. `build_worktree()` copies `input/upstream/OSTrack` into
   `output/worktree` and rewrites the config in place so that
   GOT-10k roots and the MAE checkpoint point to the input tree.
4. The upstream `tracking/train.py` is executed with the official config
   (`--script ostrack --config vitb_384_mae_ce_32x4_got10k_ep100
   --mode single --nproc_per_node 1`).  Real gradient updates happen
   inside the upstream script; optimiser and RNG state are part of the
   checkpoint it writes under `output/worktree/checkpoints`.
5. The upstream `tracking/test.py` is executed once per split with the
   latest checkpoint.  `--threads 1 --num_gpus 1` keeps sequence order
   intact -- OSTrack consumes template + search per frame and keeps
   state across frames of a sequence.
6. Result files are copied per sequence into `output/trajectories/<seq>.txt`.
7. `compute_metrics()` recomputes AO and SR@0.5 from the real validation
   annotations (`GOT10k/val/<seq>/groundtruth.txt`).
8. `output/run.json` records: device info, config, subset used,
   checkpoint path, per-stage timings, per-sequence and aggregate
   metrics.

## Continuation

`resume` reuses the latest checkpoint under
`output/worktree/checkpoints` and re-runs the tester without rebuilding
model weights.  This is the continuation contract: a new sequence is
tracked from the held model, starting from the sequence's own first-frame
box only.

## Honest limitations

* Inputs are **not** currently admitted on this host: `input/manifest.json`
  has `assets_ready: false`, and the `upstream/OSTrack/...`, MAE weights
  and GOT-10k files listed in the manifest are not present.  Consequently
  `doctor` returns 78 and `run` / `resume` refuse to spawn.  No fake data,
  no downloads, no CPU substitute is used.
* The debug scope sub-samples the real GOT-10k lists (default 4+4
  sequences) and runs 1 epoch.  This is not the reference-large 100-epoch
  full-split run; passing the debug scope does **not** imply passing the
  native 100-epoch full-split program.
* Real synchronized timings can only be recorded once CUDA is visible and
  the assets are admitted; the code path is in place and will report them
  through `run.json` when run.
* The config-patching step uses path-pattern rewriting (`*GOT10k*`,
  `*mae_pretrain_vit_base.pth`).  If the upstream config ships the data
  root under an unexpected name, patching falls back to the file content
  present in the input and the resulting `output/config_used.yaml` should
  be inspected before re-running.
* The trajectory collector picks the file whose parent directory matches
  the sequence id.  If the upstream tester uses a different output
  layout, no trajectory is copied and the metric report marks the
  sequence as `missing`.
