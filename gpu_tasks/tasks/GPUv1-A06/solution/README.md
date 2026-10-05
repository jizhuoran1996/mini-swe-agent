# GPUv1-A06 debug variant — Wav2Vec2 masked latent contrastive pretraining

## Scope
This is the `debug_only` variant. Instead of the Libri-Light unlab-6k corpus
(≈5770 h), it consumes the **16 real 16 kHz LibriSpeech dev-clean recordings**
listed in `input/train.jsonl` (and the 8 held-out recordings in
`input/validation.jsonl`). Everything runs on a single CUDA device.

## Method
* Model: `Wav2Vec2ForPreTraining` loaded from `/models/facebook--wav2vec2-base`.
  The base transformer weights are reused; the quantizer / contrastive head is
  re-initialised by `from_pretrained` (standard for this objective when starting
  from a CTC checkpoint).
* Objective: the official Wav2Vec2 **masked-latent contrastive loss**
  (`contrastive_logits_temperature`, `num_negatives = 100`) **plus the
  codevector diversity loss** produced by the vector quantizer. No waveform MSE
  and no ASR labels are used.
* Masking: `mask_time_prob` / `mask_time_length` taken from the checkpoint
  config. Spans are drawn with the official sampling rule and are **never**
  placed on padded time positions (verified at every step).
* Negatives: `_sample_negative_indices` (or random time indices) of shape
  `(B, T, K)`.
* Every recording is truncated to its first 4 s (`MAX_SAMPLES = 64000`) and
  participates in at least one real optimizer update. Batch size 4 × 4 steps =
  all 16 recordings contribute to a gradient update.
* CUDA forward + backward is mandatory; the program aborts with a non-zero exit
  code if CUDA is missing. The feature encoder is frozen following the official
  recipe; transformer, projections and quantizer are updated.

## Usage
```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py train  --input input --output output
python solution/main.py encode --checkpoint output/checkpoint \
                               --input input/validation.jsonl \
                               --output output/reloaded
```

## Outputs
* `output/checkpoint/` — HF `Wav2Vec2ForPreTraining` checkpoint plus a
  `Wav2Vec2FeatureExtractor` config.
* `output/training_state.pt` — AdamW state, optimizer step, torch / CUDA / numpy
  RNG states, seed.
* `output/run.json` — configuration, per-step **contrastive / diversity / total
  loss**, **mask count**, **negative count**, truncation and synchronized
  timing, parameter hashes proving weights changed.
* `output/reloaded/features.npy` — `(8, 768)` float32, attention-mask mean
  pooled, **L2 normalized**.
* `output/reloaded/features_meta.json` — shape, dtype, ids, pooling description.

## Doctor
`python solution/main.py doctor --input input` inspects the required jsonl files,
resolves every referenced wav, checks the model directory and CUDA availability,
reports every missing item and returns exit code `78` when anything is missing
(`0` when everything is present). It never loads model weights.

## Honest limitations
* Debug scale: 16 train / 8 held-out recordings, 4 s each, one epoch. This is
  **not** a quality or coverage statement about the reference-large Libri-Light
  run; the reference-large corpus, model scale and hardware targets are not
  exercised here.
* No ABX / WER evaluation is performed by this variant. The deliverable is the
  updated encoder plus reproducible features for the held-out recordings; the
  features can be recomputed bit-identically from the saved checkpoint.
* The base checkpoint is a CTC model, so the contrastive head is re-initialised
  — that is expected and consistent with the task's requirement to run the
  pretraining objective itself.