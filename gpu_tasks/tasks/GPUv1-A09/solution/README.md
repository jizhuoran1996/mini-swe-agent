# GPUv1-A09 — Reloadable QA Dual Encoder (BERT-tiny, CUDA)

Trainable, reloadable **question/passage dual encoder** for SQuAD-style QA retrieval, built on
`/models/prajjwal1--bert-tiny` (pinned revision `6f75de8b60a9f8a2fdf7b69cbd86d9e64bcb3837`).
This is the *debug* variant of the task (see `input/manifest.json`): 100 SQuAD train pairs
(21 distinct contexts) and 24 validation rows.

## Entry points

```bash
# 1) train + export deliverables into output/
python solution/main.py train  --input input --output output

# 2) fresh-process reload + re-encode (consistency check artefact)
python solution/main.py encode --checkpoint output/checkpoint \
                               --input input/validation.jsonl --output output/reloaded
```

`python` (not `python3`), no network, inputs/`/models` read-only, everything written under `output/`.

## Method

| item | choice |
|---|---|
| base model | `prajjwal1/bert-tiny` (2 layers, hidden 128), loaded locally (its `config.json` lacks `model_type`, so `BertConfig`/`BertModel` are used for the *base*; the exported checkpoint config includes `model_type: bert` and reloads with `AutoModel`/`AutoTokenizer`) |
| encoders | **shared** BERT-tiny for question and passage by default (spec allows shared); `--independent-encoders` gives two BERT-tiny towers saved as `checkpoint/question_encoder/` + `checkpoint/passage_encoder/` |
| max tokens | **128** (hard-coded spec value, `truncation=True`; `--max-tokens` is forced back to 128) |
| pooling | attention-mask weighted mean over `last_hidden_state`, then **L2 normalisation** (`eps=1e-8`), at train *and* encode time |
| loss | in-batch contrastive cross entropy with learnable CLIP-style temperature (`log 1/0.07`), multi-positive mask |
| multi-positive | positives are rows whose **whitespace-normalised context content is identical** — a repeated passage is never used as a negative |
| batches | each epoch shuffles all 100 rows, fills batches (size 8) with distinct passage contents first and only then tops up with same-content rows (true positives handled by the mask): **every row is seen exactly once per epoch**, duplicates never become false negatives |
| optimisation | AdamW, lr 5e-5, wd 0.01, grad-norm clip 1.0, fp32, CUDA backward, 20 epochs = 260 steps = 20 complete passes over the training set, seed 1234 |
| evaluation | cosine top-k over **unique passage content groups** (all validation ids that share a passage are one group); correctness is group-based |

Validation split note: all 24 validation rows share a single passage content, so the
validation **Recall@1 / Recall@5 are 1.0** (every retrieved passage belongs to the gold content
group). To give an honest, non-degenerate training signal the run also reports an auxiliary
probe on the training rows (`train_retrieval_probe`): question → unique-train-context retrieval
(21 candidates) scored by content group:

| model | Recall@1 | Recall@5 |
|---|---|---|
| base BERT-tiny | 0.48 | 0.87 |
| trained checkpoint | **1.00** | **1.00** |

## Artifacts written by `train`

```
output/
├── checkpoint/               HF BertModel (model.safetensors, config.json, tokenizer files,
│                             vocab.txt, encoder_meta.json with shared/pooling/max_tokens/hashes)
├── training_state.pt         seed, device (cuda), epochs/steps/samples_seen/full_passes_completed,
│                             loss history, first-step grad norm, optimizer state, init/final
│                             parameter hashes + norms, train retrieval probes, library versions
├── question_embeddings.npy   (24, 128) float32, validation order, L2-normalised
├── passage_embeddings.npy    (24, 128) float32, validation order (one per row's gold context)
├── retrieval.json            cosine top-k, per-query ranked passage groups + ids,
│                             recall@1 / recall@5, content-group judgement flags
└── run.json                  full config + metrics + artifact sha256/records
```

`encode` writes `question_embeddings.npy`, `passage_embeddings.npy`, `retrieval.json`,
`run.json` into its `--output` directory (e.g. `output/reloaded/`) from the checkpoint alone.

## Verified properties (fresh processes, RTX 5090, torch 2.11 / transformers 5.12)

* **weights updated**: checkpoint vs. base BERT-tiny — max |ΔW| ≈ 9.5e-3, all parameter names
  present, `params_updated=True`, init/final parameter hashes differ.
* **normalisation**: all embedding row norms ∈ [1−6e-8, 1+4e-8].
* **coverage**: `question_embeddings.npy`, `passage_embeddings.npy` have exactly `len(validation.jsonl)`
  = 24 rows in validation order; `retrieval.json` has one entry per row.
* **CUDA backward**: `device=cuda_used=True`, first-step grad norm ≈ 8.08, optimizer state in
  `training_state.pt`, loss 1.39 → 0.002 (last step; 0.05 epoch mean) within one run.
* **fresh-process encode consistency**: `output/` and `output/reloaded/` artefacts are
  **bit-identical** (identical sha256 for both `.npy` files and `retrieval.json`); an independent
  script that reloads the checkpoint with `AutoModel`/`AutoTokenizer`, re-implements mean pooling
  and L2 normalisation, and recomputes embeddings matches the stored arrays to ≈2.6e-7.
* **padding invariance**: batched vs. single-sequence encoding differs by ≈1.3e-7 (mask-based pooling).
* **multi-positive / content groups**: decoded indices are de-duplicated by passage content; the
  batch builder never places a duplicated passage as a negative, and `retrieval.json` records the
  full id list of each content group.
* **determinism**: two fresh training runs with the same seed yield identical final parameter
  hashes.
* **reloadability**: `AutoConfig.from_pretrained(output/checkpoint)` →
  `model_type=bert`, `AutoModel`/`AutoTokenizer` load offline (tokenizer saved fast + `vocab.txt`
  fallback).

## Hyper-parameters

`--epochs 20 --batch-size 8 --lr 5e-5 --weight-decay 0.01 --temperature 0.07 --seed 1234`
(defaults; `--device` defaults to CUDA when available). Total runtime ≈ 6 s for train + encode on
the provided debug inputs.
