# GPUv1-B08 - VideoMAE SSv2 fine-tune adapter

Source-native adapter around the official VideoMAE entry point
`upstream/VideoMAE/run_class_finetuning.py` (recipe:
`scripts/ssv2/videomae_vit_base_patch16_224_tubemasking_ratio_0.9_epoch_2400/finetune.sh`,
ViT-Base, 16 frames, 224 input, 174 SSv2 classes).

## Entries

```
python solution/main.py --help
python solution/main.py doctor  --input input
python solution/main.py run     --input input --output output
python solution/main.py resume  --input input --output output
python solution/main.py predict --input input --output output --checkpoint output/ckpt/checkpoint-best.pth [--csv input/ssv2/val.csv]
```

`--help` never imports torch/timm/decord, so it is always available.

## Inputs consumed (all from the read-only `input/`)

Declared by `input/manifest.json`:

* `upstream/VideoMAE/run_class_finetuning.py`
* `videomae_pretrained.pth`
* `ssv2/train.csv`, `ssv2/val.csv`
* `ssv2/videos/` (real mp4 clips)
* python modules: `torch`, `timm`, `decord`, `einops`

## doctor

Inspects the exact file list, hashes files <= 1 GiB, imports every required module, probes
CUDA, and prints a JSON report plus `verdict`. Exit code `78` if **any** file, module or CUDA
device is missing; `0` only when everything is available. It never loads model weights.

## run

1. Re-checks the manifest before anything else. Missing assets -> full report + exit 78, the
   upstream job is never spawned.
2. Requires a real CUDA device (exit 4 otherwise). No CPU fallback exists.
3. Writes `output/label_map.json` (174 entries, parsed from the real `train.csv`) and
   `output/sampling_config.json` (the source recipe: 16 frames, sampling_rate 4, 224 input,
   3 crops x 2 segments test view).
4. Launches `run_class_finetuning.py` with the source hyper-parameters (adamw, lr 1e-3,
   betas 0.9/0.999, wd 0.05, 30 epochs, `--save_ckpt_freq 1`, `--test_num_segment 2
   --test_num_crop 3`), single-process single-GPU (`RANK=0 WORLD_SIZE=1 LOCAL_RANK=0`), log
   tee'd to `output/logs/train.log`.
5. Reloads the produced checkpoint, compares pretrained vs finetuned tensors to prove real
   parameter updates happened, and records whether optimizer/epoch state is present.
6. Decodes every `val.csv` clip with `decord`, samples genuine distinct frame indices per
   segment (VideoMAE uniform-span + stride sampling), builds the declared crops, averages
   softmax over all views, and writes
   `output/val_clip_predictions.jsonl` (clip id, 174-dim normalised probs, pred, top5,
   frame indices, frame difference) and `output/val_report.json`.
7. Writes `output/run.json` with seed, device, upstream command, stage timings, parameter-update
   evidence and completion events.

## resume

`resume` locates the newest checkpoint in `output/ckpt/` and re-invokes the upstream script
with `--resume <path>` so model + optimizer state are restored before further updates. It
fails with exit 5 if no checkpoint exists. RNG seeding is passed through (`--seed`).

## predict

Batch entry point for new clips: reloads a trained checkpoint and evaluates any csv in the
same `id/label` format, emitting `output/clip_predictions.jsonl`. The view configuration is
identical to the validation path (same crops, same segments) - different backends may not use
different test crop/segment counts.

## Ground rules honoured

* No fabricated videos, labels, weights or one-hot probabilities.
* No deletion of clips that fail to decode - decoding errors abort the run.
* Degenerate videos (all decoded frames identical, i.e. static frame repeated) are flagged in
  `val_report.json`, not silently accepted.
* Different temporal frames per segment, never one frame replicated across the clip.

## Honest limitations

* `input/manifest.json` currently declares `assets_ready: false` and the upstream VideoMAE
  source, the pretrained checkpoint and the SSv2 videos are **not mounted**. Consequently
  `doctor` returns 78 and `run`/`predict` refuse to start; no result is claimed.
* The debug schedule is a short fine-tune that only exercises decoding, labels and checkpoint
  writing. It is **not** the source 30-epoch / 64-GPU reference-large result and must not be
  reported as such.
* On a single RTX 5090 the per-GPU batch size differs from the source 64-GPU recipe; the
  effective batch is recorded in `run.json` (`per_gpu_batch`, `world_size`). Full-batch
  calibration on 8x40-80 GiB GPUs is out of scope here.
