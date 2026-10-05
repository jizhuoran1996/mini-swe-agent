# GPUv1-A03 (debug variant) — offline English→German Marian fine-tune

Fine-tunes the provided Marian checkpoint `/models/Helsinki-NLP--opus-mt-en-de`
(revision `6183067f769a302e3861815543b9f312c71b0ca4`) on the 64 real WMT14
EN/DE sentence pairs in `input/train.jsonl` with **CUDA seq2seq teacher
forcing**, and delivers a self-contained, reloadable HF checkpoint plus an
offline translation of the 8 official `input/validation.jsonl` pairs.

This is the **debug-only** variant described in `input/manifest.json`
(64 train / 8 validation sentences, pretrained Marian instead of full source
Transformer training). It is not a claim of reference-large / benchmark quality.

## Files

| path | content |
| --- | --- |
| `solution/main.py` | all logic (train / translate / evaluate), written for this task |
| `output/checkpoint/` | HF checkpoint: `config.json`, `generation_config.json`, `model.safetensors`, `source.spm`, `target.spm`, `vocab.json`, `tokenizer_config.json` |
| `output/training_state.pt` | AdamW state, `step`, RNG states (python/numpy/torch/cuda), hyper-params |
| `output/translations.jsonl` | `id`, `en`, `translation`, `token_ids` for all 8 validation rows |
| `output/run.json` | before/after loss, hashes, real parameter counts, synchronised timings |
| `output/quality_debug.json` | self-computed debug chrF/BLEU (not an official benchmark) |
| `output/translate_run.json` | synchronised translate timing |

## Commands (exactly as specified)

```bash
python solution/main.py train     --input input --output output
python solution/main.py translate --checkpoint output/checkpoint \
                                  --input input/validation.jsonl \
                                  --output output/translations.jsonl
# optional extras
python solution/main.py translate ... --timing output/translate_run.json
python solution/main.py evaluate --translations output/translations.jsonl \
                                 --input input/validation.jsonl \
                                 --output output/quality_debug.json
```

## Training recipe (implemented in `main.py`)

* fixed seed `20240517` (python/numpy/torch/cuda), `cudnn.deterministic=True`;
* `max_length = 128` (`truncation=True`) for source **and** target;
* target labels = decoder token ids with padding replaced by `-100`
  (`IGNORE_INDEX`); source padding uses the model `<pad>` id `58100`;
* teacher forcing: `MarianMTModel(input_ids, attention_mask, labels)`
  (the HF layer applies the standard shifted cross-entropy, ignoring `-100`);
* AdamW, `lr = 2e-5`, `batch_size = 8`, `epochs = 3`, grad-norm clip 1.0 →
  **24 optimizer steps**; every one of the 64 training sentences receives
  **3** parameter updates (`min_optimizer_updates_per_train_sentence = 3`);
* before-loss measured on the frozen pretrained weights, after-loss measured
  with the very same token-weighted teacher-forcing recipe in `eval()` mode;
* all timings are taken around `torch.cuda.synchronize()`.

Recorded numbers: teacher-forcing NLL on the 64 training pairs
**5.5129 → 3.4456** (PPL 247.9 → 31.4); validation pairs 5.3953 → 4.4697.
Only the two *static* sinusoidal position-embedding tensors are unchanged
(the model uses `static_position_embeddings`), every learnable tensor moved.

## Translation

* source-only inference: each validation row is tokenised from its `en` field
  alone — the reference `de` is never placed in the prompt (checked: 0 leakage);
* beam search (`num_beams=4`, `do_sample=False`), `max_new_tokens=128`;
* `token_ids` are the generated target ids with the decoder-start prefix and
  `<eos>`/`<pad>` tail stripped; `translation` is the decode of those ids;
* empty output is a hard error (non-zero exit), and row count/ids are asserted
  to cover the input exactly.

### Verified properties (independent re-check, fresh Python processes)

* checkpoint reloads with `MarianMTModel`/`MarianTokenizer` **and**
  `AutoModelForSeq2SeqLM`/`AutoTokenizer` (vocab 58101);
* re-computed teacher-forcing NLL from the saved checkpoint = `run.json`
  `after_loss` (3.4456) and from the base model = `before_loss` (5.5129);
* re-running `train` with the same seed reproduces bit-identical step losses
  and `after_loss`; re-running `translate` in a new process yields identical
  `token_ids` and strings for all 8 rows;
* `run.json` source hashes match the delivered `input/*.jsonl`;
* `training_state.pt` contains optimizer/step/RNG.

## Honest scope

`chrF ≈ 56.1` / `BLEU ≈ 21.6` (self-implemented corpus metrics in `main.py`,
computed against the 8 validation references) are a **debug smoke signal** that
a real model was executed and improved, not a validated WMT benchmark result.
No external metric library or reference-large training is available in this
offline container.
