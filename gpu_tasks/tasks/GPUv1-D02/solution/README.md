# GPUv1-D02 — GovReport summarization with Qwen2.5-0.5B-Instruct (CUDA)

Debug variant of the government-report summarization task. 16 genuine
GovReport *test* reports (`input/requests.jsonl`, fields `id`/`document`, no
reference summaries) are summarized with the local CUDA checkpoint
`/models/Qwen--Qwen2.5-0.5B-Instruct`
(revision `7ae557604adf67be50417f59c2c2f167def9a775`, read from the model
`asset_lock.json`). This is **not** the reference-large run.

## What is implemented

| Spec item | Where |
|---|---|
| `python solution/main.py run --input input --output output` | `main.py cmd_run` |
| `python solution/main.py infer --input input/requests.jsonl --output output/reloaded.jsonl` | `main.py cmd_infer` |
| `--serve` HTTP service (`/health`, `POST /infer {id,document}`) | `main.py serve` / `_Handler` |
| `summaries.jsonl` = `id/summary/token_ids/input_token_count/truncated` (+ extras) | `cmd_run` |
| `run.json` = actual revision, parameters, GPU-stage timings, coverage | `cmd_run` |
| Independent checks + ROUGE/correctness report | `solution/verify.py` |

### Decoding contract (reproducible greedy)

* Report text is tokenized with the Qwen tokenizer (`add_special_tokens=False`)
  and the **first 2048 tokens** are kept (`truncated=true` when longer).
* Prompt = Qwen chat template with a system instruction and a user instruction
  "Write a concise, faithful summary … in 3 to 5 sentences"; the document token
  span is spliced in exactly between the tokenized head/tail of the template
  (no BPE merges across the document boundary).
* Generation: `do_sample=False`, `num_beams=1`, `repetition_penalty=1.0`,
  `use_cache=True`, `max_new_tokens=128`, bfloat16, single RTX 5090.
* `token_ids` are the raw newly generated ids (including a terminal EOS if
  produced); `summary` is their decoded text.
* The model is only ever used through this decode path — summaries are model
  output, never a prefix or substring lifted from the document.

## Run

```bash
python solution/main.py run  --input input --output output
python solution/main.py infer --input input/requests.jsonl --output output/reloaded.jsonl
# keep-alive service (ready only after the real CUDA model load):
python solution/main.py run   --input input --output output --serve --port 8000
python solution/main.py serve --input input --output output --port 8000
# independent verification + quality/correctness report:
python solution/verify.py --input input --output output
```

`run --serve` performs the batch run, then serves new queries with the same
in-memory CUDA model. `/health` returns `{"ready": true, "device": "cuda", …}`
only once the model is loaded. `SIGTERM`/`SIGINT` shut the server down cleanly
(exit code 0, socket closed, `output/serve.json` marked `active:false`).

## Outputs

* `output/summaries.jsonl` — one row per report id (16/16, complete coverage).
* `output/run.json` — model repo + actual revision, decoding parameters, prompt
  template, per-stage GPU timings (model load / tokenize / generate), peak CUDA
  memory, coverage counts.
* `output/reloaded.jsonl` — `infer` re-runs the same pipeline after reloading
  the checkpoint from disk.
* `output/verification.json` — independent checks: coverage, reload equality,
  token-by-token greedy recomputation (hand-written KV-cache argmax loop),
  live HTTP service (`/health` after CUDA load, new request, request after
  idle, clean SIGTERM).
* `output/quality_report.json` — summary/correctness report. Because the input
  has **no reference summaries**, reference ROUGE is explicitly reported as
  *not computable*; only intrinsic checks are given (emptiness, document
  substring/prefix copying guard, compression, distinct-n-gram, lexical
  overlap vs. the source document). No formal quality/ROUGE pass is claimed.

## Verified results (RTX 5090, torch 2.11+cu129, transformers 5.12)

* coverage: 16/16, no missing/extra/duplicate ids.
* reload equality: `reloaded.jsonl` token_ids and summaries identical to
  `summaries.jsonl`.
* greedy token recomputation: 16/16 reports reproduce `token_ids` exactly with
  an independent token-by-token argmax loop.
* service: `/health` ready after CUDA load, new report summarized, another
  request answered after 5 s idle, HTTP 400 on malformed body, SIGTERM exit 0
  with the port closed.
* copying guard: 0/16 summaries are an exact substring or prefix of their
  source document (all are decoded model output).
