# GPUv1-A10 — Reusable encyclopedic text encoder (BERT-tiny MLM on WikiText-2)

CUDA masked-language-model training of `prajjwal1/bert-tiny` on the real
WikiText-2 paragraphs in `input/train.jsonl`, plus a mean-pooled normalized
encoder exposed through `embed`.

## Commands

```bash
python solution/main.py train --input input --output output
python solution/main.py embed --checkpoint output/checkpoint \
    --input input/validation.jsonl --output output/embeddings.npy
```

`--input` for `train` accepts a directory containing `train.jsonl` /
`validation.jsonl` (or a jsonl file). Everything runs on `cuda` when available.

## What is implemented

* **Standard BERT MLM head** — the unmodified `BertForMaskedLM`
  (`BertModel` + `BertOnlyMLMHead`) initialized from `/models/prajjwal1--bert-tiny`.
  The base `config.json` has no `model_type`, so the model is loaded with
  `BertForMaskedLM`; the saved checkpoint adds `model_type="bert"` and reloads
  with `AutoModelForMaskedLM`.
* **Tokenization** — `BertTokenizerFast`, `max_tokens=128`, truncation.
  Candidate positions for masking are only real word tokens: both the
  `[CLS]`/`[SEP]` special tokens and padding are excluded.
* **Masking** — per example, `mask_rate=0.15` of the candidate tokens are
  selected (with a seeded NumPy generator). Of the selected tokens:
  80% → `[MASK]`, 10% → random vocab id, 10% → left unchanged. Labels are the
  original ids at selected positions and `-100` everywhere else, so **padding
  and unselected tokens never contribute to the loss**.
* **Training** — `AdamW`, grad clipping, deterministic shuffling per epoch and a
  fresh seeded mask every epoch (dynamic masking). At least one full pass over
  the training set is guaranteed (30 epochs × 98 examples ≈ 390 steps).
  Fixed seed = 1234 for Python / NumPy / Torch / CUDA RNGs.
* **Validation loss** — a *fixed* mask (seed `[1234, 10000]`) is applied once to
  the validation set; the reported loss is the token-weighted average over the
  masked positions, so padding cannot dilute the mean.

## Determinism / reproducibility

Given the fixed seed, training and embedding are bit-reproducible. Embedding
uses `model.eval()` (dropout off) and `torch.no_grad()`, so re-running `embed`
in a fresh process yields identical `embeddings.npy`.

## Deliverables (written to `output/`)

| Path | Content |
| --- | --- |
| `output/checkpoint/` | standard HF checkpoint (`config.json`, `model.safetensors`, tokenizer files) |
| `output/training_state.pt` | optimizer state, `global_step`, epoch, seed, RNG states (Python/NumPy/Torch/CUDA) |
| `output/validation_mlm.json` | fixed-seed mask: `loss`, `masked_tokens` (443), `num_examples`, `mask_rate`, `max_tokens` |
| `output/embeddings.npy` | `(31, 128)` float32, one L2-normalized mean-pooled vector per real validation paragraph |
| `output/run.json` | config, seeds, step counts, per-epoch losses, validation loss, versions, device |

### `embed` details

Each validation line is encoded with the checkpoint encoder
(`model.bert`); the mean pool is `sum(h * attention_mask) / sum(attention_mask)`
(padding excluded) and the result is L2-normalized. Row order matches
`validation.jsonl`, so all 31 paragraphs are covered.

### `training_state.pt`

Stored as plain Python types for the NumPy RNG state so the file also reloads
with `torch.load(path)` (default `weights_only=True`). The optimizer state
restores into a freshly constructed `AdamW`; the NumPy state restores with
`np.random.set_state((name, np.asarray(keys, np.uint32), pos, has_gauss, cached_gaussian))`.
