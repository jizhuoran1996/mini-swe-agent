# GPUv1-A04 (debug) — Whisper-tiny LibriSpeech fine-tune + transcription

## What this does

Implements the debug variant of GPUv1-A04: a real CUDA teacher-forced seq2seq
fine-tune of the local `/models/openai--whisper-tiny` model on the 16 recordings
listed in `input/train.jsonl` (LibriSpeech dev-clean, real audio, official
transcripts), followed by greedy transcription of the 8 independent recordings
in `input/validation.jsonl`.

Field resolution is tolerant: audio is read from any of `audio`, `audio_path`,
`audio_filepath`, `audio_file`, `path`, `file`, `file_name`, `filename`, `wav`,
`wav_path`, `speech`, `input_audio`, or any string value ending in
`.wav/.flac/.mp3/.ogg/.m4a/.opus/.sph`. Transcript text is read from `text`,
`transcript`, `transcription`, `normalized_text`, `label`, `target`,
`target_text`, `sentence`, `reference`, `ref`, `gt`, or — as a last resort — the
longest string value that is neither the audio path nor the id.

Key protocol details:
* Standard Whisper 80-bin log-mel features (via `WhisperProcessor.feature_extractor`, 16 kHz).
* Targets are built from the training transcripts only:
  `<|startoftranscript|><|en|><|transcribe|><|notimestamps|> ...text... <|endoftext|>`.
  Batches are right-padded with `-100` so padded positions are ignored by the loss.
* Every training recording appears in at least one optimizer update; coverage is
  recorded per recording in `run.json`.
* Fixed seed via `random.seed` / `numpy.random.seed` / `torch.manual_seed` /
  `torch.cuda.manual_seed_all`. Linear warm-up LR schedule (100 steps cap).
* CUDA is required: the process exits with code 2 if `torch.cuda.is_available()` is false.
* No CPU fallback, no mock weights, no randomized substitution, no transcript lookup table.

## Usage

```bash
python solution/main.py doctor --input input
python solution/main.py train --input input --output output
python solution/main.py transcribe \
    --checkpoint output/checkpoint \
    --input input/validation.jsonl \
    --output output/transcripts.jsonl
python solution/main.py --help
```

`doctor` returns exit code `78` (EX_CONFIG) if any required file, audio, model
file, CUDA device, or Python dependency is missing, and `0` if everything is
present. It never loads model weights and prints a JSON report listing every
missing item.

## Deliverables produced

* `output/checkpoint/` — full Hugging Face `WhisperForConditionalGeneration`
  weights + `WhisperProcessor` (feature extractor + tokenizer), reloadable with
  `WhisperForConditionalGeneration.from_pretrained` and `WhisperProcessor.from_pretrained`.
* `output/training_state.pt` — optimizer state dict, LR scheduler state, global
  step, epochs, LR, seed, Python/NumPy/Torch/`torch.cuda` RNG states, per-step
  loss history, and per-recording optimizer-step coverage.
* `output/run.json` — parameters, seed, loss history, per-recording coverage and
  truncation flags, synchronized timings (total / training / post-train eval /
  checkpoint save), peak device memory, CUDA encoder+decoder backward checks,
  independent weight-diff check, and train WER with per-sample reference/prediction.
* `output/transcripts.jsonl` — `id`, `text`, `token_ids`, `duration` per validation recording.

## Environment

* Single RTX 5090, PyTorch 2.11, Transformers 5.12, NumPy, `soundfile` (with a
  stdlib `wave` fallback for PCM WAV files).
* Container is offline; only `input/` and `/models/` are read and only `solution/`
  and `output/` are written.
* No dataset download, no package install, no sudo, no shell strings from the input.

## Fix history

* The variable holding the training output directory was renamed from `out` to
  `out_dir`, and the model forward output the loss is read from was renamed to
  `model_out` / `eval_loss`. This prevents the model's `Seq2SeqLMOutput` from
  shadowing the output path (previously caused
  `TypeError: expected str, bytes or os.PathLike object, not Seq2SeqLMOutput`
  at `os.makedirs(out, ...)`).

## Honest limitations

* This is the **debug** variant — 16 train / 8 validation recordings from
  LibriSpeech dev-clean, Whisper-tiny. It is **not** the reference-large task
  (Whisper-large-v3 over the full LibriSpeech-960h split) and does not claim to be.
* The validation manifest (`input/validation.jsonl`) carries no reference
  transcripts, so validation WER cannot be computed honestly and is reported as
  `null`. The only WER reported is on the training set (greedy decode, standard
  Whisper English normalization), which serves as a training-sanity check, not as
  a held-out metric.
* Training uses fp32 on CUDA. No fp16/bf16 autocast is enabled; the mixed-precision
  capability of the GPU is not exercised here. This was a deliberate choice to keep
  numerical behaviour deterministic and avoid dtype mismatches with the fp32
  feature extractor.
* All 16 recordings are shorter than 30 s, so at most a trailing trim to 480 000
  samples can happen; any such trim is recorded per recording in `run.json`.
* Beam search, timestamp prediction, and cross-language translation are not
  implemented (the task is English transcription only).
* `main.py --help` and each sub-command's `--help` do not import torch or
  transformers and do not read any model weights.
