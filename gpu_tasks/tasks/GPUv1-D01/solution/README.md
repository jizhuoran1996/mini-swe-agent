# GPUv1-D01 (debug variant) — CUDA Qasper answer archive + reader service

Runs the eight native LongBench Qasper questions found in `input/requests.jsonl`
through **Qwen/Qwen2.5-0.5B-Instruct** (revision `7ae557...a775`, local read-only
container path `/models/Qwen--Qwen2.5-0.5B-Instruct`) on a real CUDA device, and
serves the same resident model for follow-up questions.

## Usage

```
python solution/main.py doctor --input input --output output
python solution/main.py run    --input input --output output
python solution/main.py serve  --port 8080 --input input --output output
python solution/main.py --help          # argparse help, no model load, no CUDA use
```

Useful flags: `--model PATH`, `--revision REV`, `--max-tokens 2048`,
`--max-new-tokens 128`.

## Method (exactly the specified protocol)

* Chat template via `tokenizer.apply_chat_template(..., add_generation_prompt=True)`
  with a short system prompt and the LongBench Qasper user template
  (`Document: … Question: … Answer:`).
* **Token-exact 2048-token budget on the debug 0.5B model:** instruction prefix,
  document and question tail are tokenized separately around an in-band sentinel.
  Only document tokens are dropped (head kept, like LongBench truncation); the chat
  template and the question are always preserved in full. `truncated` is reported
  per item together with `input_tokens`.
* Greedy decoding (`do_sample=False`, `num_beams=1`), `max_new_tokens=128`, KV cache on.
* BF16 weights moved to `cuda`; `torch.cuda.is_available()` is checked first and the
  process fails (exit 78) if no CUDA device exists — there is **no CPU fallback**.
* Gold answers are never read: `load_requests` only touches id/document/question fields.

## Outputs (written to `output/`)

* `answers.jsonl` — one line per question, fsynced after each item:
  `{id, answer, raw_text, token_ids, input_tokens, truncated}`
  (`raw_text` is the exact decoded model output, `answer` is the lightly cleaned
  string used for scoring; `token_ids` are the newly generated ids only).
* `run.json` — status, model/tokenizer/dtype, decoding and truncation policy,
  CUDA/torch/transformers versions, input and output SHA-256, per-item
  `torch.cuda.Event` GPU timings (synchronized) + wall times, token throughput,
  peak device memory, seeds, and honest limitations.
* `document_manifest.json`, `reader_service_config.json`, `reference_metric_inputs.json`
  — document hashes/token accounting, service contract, and predictions for the official
  `qa_f1_score` scorer (no gold labels exist in the frozen package).
* `doctor_report.json` — static preflight result.

## Service

`serve` loads the model onto CUDA **before** binding the socket, prints one JSON
`{"event":"ready","port":…}` line, then answers:

* `GET /health` → `{"status":"ready","model_loaded":true,"cuda":true,…}`
* `POST /infer` with `{"id"?, "document", "question"}` → full answer record with
  `fresh_request: true`, per-request GPU ms, and the same truncation accounting.

Missing/empty `document` or `question` is rejected with HTTP 400 **before** any
model work. Every request is tokenized and generated from scratch (no reuse of
previous outputs or KV state); requests are serialized on a lock because one GPU
holds one model. Requests are appended to `output/serve_log.jsonl`, lifecycle
events (ready/signal/stopped) to `output/serve_events.jsonl`. `SIGTERM`/`SIGINT`
trigger a graceful shutdown and exit code 0 so an idle-then-killed service is
observable.

## `doctor`

Static only — it never loads weights or runs inference. It checks: input dir,
`manifest.json`, `requests.jsonl` (parse, field extraction, count, SHA-256 vs the
frozen hash), model dir contents (`config.json`, tokenizer artifacts, weights),
importability of `torch`/`transformers`/`numpy`, and `torch.cuda.is_available()` +
device name/BF16 support. Every missing required item is listed and the exit code
is **78**; if everything is present it prints the report and returns **0**.

## Limitations (honest)

* This is the declared **debug** variant: 0.5B model, 8 native questions, 2048-token
  budget. It does not implement or claim the reference-large 32B / 200-question run.
* Accuracy (LongBench `qa_f1`) is **not** measurable here: the frozen input package
  contains no gold answers. We report coverage, per-item recomputation evidence and
  service behaviour only; scoring must be done by the evaluator.
* Truncation keeps the head of the document, so answers to questions whose evidence
  lies beyond 2048 document tokens can be incomplete; `truncated` flags these items
  and `document_manifest.json` records full vs used token counts.
* Single GPU, single process, requests serialized; no batching, no tensor parallel.
* Greedy decoding is deterministic given the same device/library stack, but exact
  text can still differ across CUDA/cuBLAS versions; the recorded SHA-256s bind the
  actual delivered run.
