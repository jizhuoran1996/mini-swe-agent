# GPUv1-D05 (debug variant) - DocVQA answer ledger with Qwen2.5-VL-3B-Instruct

## What this is

Real document-image question answering: every page image in `input/` is decoded,
resized to the fixed pixel budget, passed through the **vision encoder of the local
Qwen2.5-VL-3B-Instruct** and the question is answered by greedy text generation on
the same GPU. No OCR shortcut, no question-only reasoning, no cached predictions.

This is the **declared debug variant** (`scale = debug_only`): 8 native DocVQA
sample images/questions and the 3B model instead of the 32B full-validation
reference run. The reference-large result is **not** claimed.

## Environment expectations

* Model: `/models/Qwen--Qwen2.5-VL-3B-Instruct` (read-only), revision
  `66285546d2b821cf421d4f5eb2576359d3770cd3` (override with `DOCVQA_MODEL_PATH`).
* PyTorch + CUDA GPU, Transformers, NumPy, Pillow (already provided).
* `bfloat16` weights, `max_pixels = 262144`, `min_pixels = 3136`, image patch
  factor 28, greedy decoding with `max_new_tokens = 64`, seed 0.

## Usage

```bash
# readiness only - does NOT load weights, does NOT run inference
python solution/main.py doctor --input input        # exit 0 = ready, exit 78 = missing items

# required run
python solution/main.py run --input input --output output

# one extra, previously unseen document
python solution/main.py infer --image page.png --question "What is the invoice total?" --output out.json

python solution/main.py --help
```

The actual work **requires CUDA** and exits non-zero if `torch.cuda.is_available()`
is false. There is no CPU fallback and no mock/random weight substitution.

## Outputs (written to `output/`)

| file | content |
| --- | --- |
| `answers.jsonl` | one JSON object per request: `id`, `answer`, `token_ids`, `page_id`, `question`, `image`, `num_tokens` |
| `run.json` | model/hardware/config, per-sample timings (wall + CUDA-event ms), peak CUDA memory, H2D bytes, RNG state hash, input/output SHA-256, ANLS summary, full sample records |
| `page_manifest.json` | page id -> image and the question ids answered on that page |
| `processor_config.json` | effective image-processor config (min/max pixels, classes) |

`token_ids` are the ids actually emitted by `generate` (prompt tokens sliced off),
not synthesized text: `retokenized_ids` and `retokenized_equal` in `run.json` show
the re-encoding cross-check of the decoded answer.

## Scoring

ANLS (threshold 0.5, normalized Levenshtein) is computed **only** from independent
gold answers carried by the input records (`answers` / `gold_answers` / `answer`
fields). The model never receives them. If the debug input ships no gold answers,
`run.json` records `mean_anls: null` with an explicit note instead of inventing a
score.

## Honest limitations

* Debug scale: this run covers at most the questions present in `input/requests.jsonl`
  (8 documents in the declared debug package), not the DocVQA validation full set.
* Model is the 3B instruct checkpoint; the reference specification targets a 32B run.
* ANLS cannot verify input completeness or execution; `doctor` and `run.json`
  (CUDA-event timings, H2D bytes, memory, hashes) carry that evidence instead.
* `--limit` exists only for smoke-testing a subset; the required run uses it unset.
* Known formatting difference: if `requests.jsonl` gains extra fields, they are
  preserved in `run.json` samples but only the documented fields appear in
  `answers.jsonl`.
* Unanswerable questions are mapped to the literal reply `unanswerable`.
