# GPUv1-A05 - English speech -> German text (fairseq CoVoST2 en-de)

Source-native adapter around the frozen fairseq `s2t_transformer_s` CoVoST2
English-German recipe. All work happens inside `solution/` and `output/`; the
frozen `input/` tree is read-only and never modified.

## Status of this checkout

The input manifest declares `assets_ready: false`. On this host the only file
mounted under `input/` is `input/manifest.json`; none of the frozen files
listed below are present, and `fairseq` is not importable here.

Run:

```
python solution/main.py doctor --input input
```

It prints every missing file, module and CUDA device and exits **78** until the
native assets are mounted. `run`/`resume`/`translate` also refuse to execute in
that state (`run.json` records `status: missing_inputs`, `complete: false`).
No synthetic audio, features, weights or predictions are produced.

## Frozen inputs the adapter requires

Taken from `input/manifest.json`:

- `upstream/fairseq/train.py`
- `covost2/config_st.yaml`
- `covost2/train.tsv`
- `covost2/dev.tsv`
- `covost2/spm_unigram10000.model`
- `covost2/dict.txt`

Module requirement: `fairseq` (plus `torch`, `torchaudio`, `soundfile`,
`sentencepiece`, `sacrebleu`, `numpy`, `yaml`, reported by `doctor`).
Optional: `upstream/asr_encoder_checkpoint.pt` for `--finetune-from-model`
initialisation from the released English ASR encoder.

## Commands

```
python solution/main.py doctor    --input input
python solution/main.py run       --input input --output output [--max-update 30000]
python solution/main.py resume    --input input --output output --extra-updates 1000
python solution/main.py translate --input input --output output \
                                  --checkpoint output/speech_translation.pt \
                                  --tsv input/covost2/new_english.tsv
```

`main.py --help` and each subcommand's `--help` never touch torch/fairseq.

### doctor

Non-executing check. Prints a JSON report with `required_files`,
`present_files`, `missing_files`, `required_modules`, `missing_modules`,
`missing_dependencies`, package versions, CUDA availability, device name and
memory. Exit code **0** if everything is present, **78** otherwise.

### run

1. Verifies the frozen inputs and fairseq importability. Non-zero exit 78 if
   anything is missing. Non-zero exit 3 if `torch.cuda.is_available()` is
   False (GPU task - no CPU fallback).
2. Invokes upstream `upstream/fairseq/train.py` (or `python -m
   fairseq_cli.train` if only the installed package is available) with the
   source recipe arguments:

   ```
   --task speech_to_text --criterion label_smoothed_cross_entropy
   --arch s2t_transformer_s --optimizer adam --adam-betas (0.9,0.98)
   --lr 0.002 --lr-scheduler inverse_sqrt --warmup-updates 4000
   --clip-norm 10.0 --label-smoothing 0.1 --fp16 --seed 1
   --max-update 30000 --save-interval-updates 1000
   --config-yaml covost2/config_st.yaml
   ```

   `checkpoint_last.pt` written by fairseq contains model, optimizer,
   learning-rate scheduler, meters and RNG state. If
   `upstream/asr_encoder_checkpoint.pt` exists it is passed via
   `--finetune-from-model`; the source recipe's 1000-update encoder-freeze
   window is preserved as a declared intent in `run.json` under
   `recipe_declaration`. It is never used to skip real gradient updates.
3. Averages the last up-to-5 interval checkpoints with upstream
   `scripts/average_checkpoints.py` (falls back to `checkpoint_last.pt` if the
   averaging script is unavailable).
4. Exports `output/speech_translation.pt` and
   `output/checkpoint_lineage.json` (SHA256 of every input and output
   checkpoint).
5. If a paired test TSV exists (`--test-tsv`, else `covost2/test.tsv`,
   `covost2/test_st_en_de.tsv`, else `covost2/dev.tsv`) it is staged into
   `output/staged_covost2/` alongside symlinks to the frozen covost2 assets and
   decoded with upstream `generate.py` (`--beam 5`, `--max-tokens 8000`).
   Predictions are written to `output/test_translations.jsonl` as
   `{"audio_id": ..., "prediction": ..., "reference": ...}` in original
   order. sacreBLEU (13a tokeniser) is computed if the TSV carries targets and
   saved to `output/sacrebleu.json`.

### resume

Reads `output/checkpoints/checkpoint_last.pt`, extracts the current update
counter from `optimizer_history[-1]["num_updates"]`, sets
`--max-update = current + extra_updates` and re-enters the same training
pipeline. Optimizer, scheduler and RNG state are loaded straight from the
fairseq checkpoint, so no warmup restart happens. Exits 2 if no checkpoint is
present - it never silently restarts from scratch.

### translate

For a *new* frozen English TSV: stages the covost2 directory as a symlink farm
with the new TSV installed as `test.tsv`, runs upstream `generate.py` against
the exported checkpoint, and writes `output/test_translations.jsonl` plus, if
the TSV carries targets, `output/sacrebleu.json`. Input audio paths resolve
through the TSV's relative-path semantics so the acoustic encoder path is
really exercised - no reference transcript or German text is ever fed to a
text-only decoder.

## Outputs written to `output/`

- `run.json` - status, seed, recipe declaration, device, package versions,
  timings, checkpoint lineage, BLEU, completion flag.
- `train_command.json` - exact upstream invocation (no arbitrary shell).
- `train.log`, `generate.log`, `average.log` - raw upstream logs.
- `checkpoints/checkpoint_last.pt` - resumable training state.
- `speech_translation.pt` - averaged / exported translator.
- `checkpoint_lineage.json`.
- `test_translations.jsonl` - `audio_id` + German prediction, order preserved.
- `sacrebleu.json` (when references exist).

## Honest limitations

- This run is the **native debug** adapter. It does not claim reference-large
  numbers. The reference-large plan (full CoVoST2 en-de, 30000 updates,
  T3-class hardware) is preserved in the task spec and is not executed here.
- The host inspected by this checkout has no frozen assets and no CUDA device
  visible, so no training, averaging, generation or BLEU number is produced
  here; `doctor` and `run` honestly report the gate as unmet.
- The 1000-update encoder-freeze window and en-* `max_tokens` are recipe
  declarations carried in `config_st.yaml`/`run.json`, not reimplemented
  inside this adapter.
