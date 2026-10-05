# GPUv1-A08 — GovReport LoRA adapter for Qwen2.5-0.5B-Instruct

Debug-scale variant of the long-report summarization task. The pipeline fine-tunes a
frozen `Qwen/Qwen2.5-0.5B-Instruct` (revision `7ae557604adf67be50417f59c2c2f167def9a775`,
container path `/models/Qwen--Qwen2.5-0.5B-Instruct`) with a CUDA LoRA adapter on the
32 authentic GovReport report/summary pairs in `input/train.jsonl`, then summarizes the 4
official test reports in `input/validation.jsonl`.

## Commands

```bash
python solution/main.py train     --input input --output output
python solution/main.py summarize --adapter output/adapter \
                                  --input input/validation.jsonl \
                                  --output output/summaries.jsonl
```

Both commands were executed in this container on an RTX 5090 with PyTorch 2.11,
Transformers 5.12 and PEFT 0.21.2. `train` runs in ~8 s, `summarize` in ~10 s.

## What the implementation does

| Requirement | Implementation |
| --- | --- |
| CUDA LoRA, rank 8, `q_proj`/`v_proj` | `LoraConfig(r=8, lora_alpha=16, lora_dropout=0.0, bias="none", target_modules=["q_proj","v_proj"], task_type="CAUSAL_LM")`; 96 tensors / 540,672 trainable params |
| Base model frozen | all base params `requires_grad=False`; fingerprint of every non-LoRA parameter is hashed before and after training and compared (must be equal) |
| Report = first 384 tokens | report tokenized, sliced to `[:384]`, decoded, inserted into the chat prompt (`--max_report_tokens 384`) |
| Summary ≤ 128 tokens | reference summary sliced to `[:128]` and used as target together with the closing `<|im_end|>` |
| Only assistant summary in loss | `labels = [-100] * n_prompt + target_ids`; an assertion guarantees prompt/padding positions are exactly `-100` and every target token is supervised; padded positions stay `-100` |
| Every report used ≥ once | 6 epochs × 16 batches (batch size 2); per-report occurrence counts asserted non-zero and logged in `run.json` |
| Fixed seed | `SEED=42`, Python/NumPy/Torch/CUDA seeds set; batch order from a seeded `random.Random(42 + epoch)`; full fp32 training plus deterministic kernels so two runs produce bitwise-identical adapters (verified) |
| Small context / quality reported separately | `run.json → generation.context_stats`, `base_only_baseline`, `validation_loss` (see below) |

Training: AdamW, lr 3e-4 with 5-step warmup + cosine decay, 96 steps, grad-norm clip 1.0,
full-precision (no bf16 autocast) for reproducible numerics. Every loss value is checked
finite; a non-finite loss or gradient norm aborts the run.

## Deliverables

```
output/
├── adapter/                      # standard PEFT adapter (adapter_config.json + adapter_model.safetensors)
├── training_state.pt             # optimizer state_dict, step=96, RNG states, base model repo/revision/path
├── summaries.jsonl               # 4 rows: id, text, token_ids (+ prompt_token_ids, prompt_sha256)
└── run.json                      # full config, loss curve, coverage, checks, quality report
```

`summaries.jsonl` also stores the exact `prompt_token_ids` and `prompt_sha256` of each
generation prompt so that the "reference summary never enters the prompt" property is
directly checkable. Generation is greedy (`do_sample=False`, `num_beams=1`,
`max_new_tokens=128`, `repetition_penalty=1.0`) and therefore reproducible.

## Verification performed (all passed)

1. **Base weights untouched** — `model.safetensors` SHA-256 is
   `fdf756fa…` both before and after training and matches `asset_lock.json`; the
   fingerprint of all non-LoRA parameters is identical before/after training and when
   the adapter is loaded again from disk in a fresh process.
2. **Label masking / truncation** — for all 32 train rows: prompt labels `== -100`,
   every target label supervised, last target token `== <|im_end|>` (151645),
   report prefix ≤ 384 tokens, target ≤ 129 tokens (128 summary + EOS).
3. **Coverage** — 32/32 unique reports used, minimum 6 occurrences each (6 epochs),
   `run.json → coverage.all_reports_used = true`.
4. **Finite loss** — 96/96 recorded losses finite (epoch means 2.487 → 2.3468 → 2.2374 →
   2.1482 → 2.0950 → 2.0743); `training_state.pt` holds 96 optimizer state groups,
   `step = 96`, RNG states for Python/NumPy/Torch/CUDA and the base model reference.
5. **Adapter non-zero** — 96 LoRA tensors, L2 norm 11.8948, max |w| 0.0479, none all-zero.
6. **Fresh-process determinism** — `summarize` was run three times in separate processes;
   `token_ids` are identical (128 tokens per validation report). Independently, loading
   base + adapter with vanilla `transformers` + `peft` and greedy decoding with the
   settings recorded in `run.json` reproduced the stored `token_ids` exactly for all 4 rows.
7. **No reference in prompt** — validation prompts are built from the document only; the
   stored `prompt_token_ids` match a document-only chat prompt, and every
   `prompt_contains_reference_summary` flag is `false`.

## Quality report (small context, small model — debug scale only)

Context facts (from `run.json → generation.context_stats`): the validation reports
average **11,782 BPE tokens**, while only the first **384** are given to the model
(**3.3 %** of each document); the 4 reference summaries average **704 BPE tokens**
(none fits the 128-token target cap, so at best ~18 % of a reference is representable).

| Metric (greedy, 4 validation rows) | LoRA adapter | Base model (adapter disabled) |
| --- | --- | --- |
| ROUGE-1 F1 | 0.1812 | 0.1894 |
| ROUGE-2 F1 | 0.0375 | 0.0411 |
| ROUGE-L F1 | 0.1133 | 0.1089 |
| Teacher-forced summary-token loss | **2.3974** | 2.5936 |

The adapter reduces teacher-forced cross-entropy over the supervised summary tokens of the
official validation rows by **0.196 (7.6 %)** despite never seeing them, and its greedy
outputs share only 0.27 token-set Jaccard with the base model, i.e. it clearly changes
behaviour. N-gram ROUGE differences are within noise for 4 examples (and ROUGE is a poor
proxy when the source is truncated to 3 % of its length), so they should be read as a
pipeline sanity signal, not as a quality claim.

Expected failure modes of this debug configuration: the model only sees the report's
opening section and therefore summarizes the document's framing rather than its full
findings; generated summaries run to the 128-token cap without emitting `<|im_end|>`;
and 32 training pairs are far too few to teach abstractive compression. This submission
does **not** claim reference-large results (`formal_large_tested = false`); the original
large-scale specification is out of scope for the debug container.
