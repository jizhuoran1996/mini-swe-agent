# GPUv1-D04 (debug variant) — natural-language SQLite query tool

Local CUDA deployment of `Qwen/Qwen2.5-Coder-0.5B-Instruct` that turns database
questions into read-only SQLite queries, executes them for real and archives the SQL,
model raw output/token ids and execution results.

## Usage

```bash
# Inspect inputs/dependencies only (loads no weights); exit 0 = ready, 78 = missing
python solution/main.py doctor --input input

# Required run: generate + execute for all questions in input/requests.jsonl
python solution/main.py run --input input --output output

# New question against any SQLite database
python solution/main.py query --database input/chinook.sqlite \
    --question "How many invoices are there?" --output output/new_query.json

python solution/main.py --help
```

## What the run does

1. `doctor`-style input checks: `schema.sql`, `chinook.sqlite`, `requests.jsonl`,
   `manifest.json` must exist; SHA-256 is compared against `manifest.json`.
2. Model loaded from the read-only `model_container_path` in `manifest.json`
   (`/models/Qwen--Qwen2.5-Coder-0.5B-Instruct`), pinned revision, bfloat16 on CUDA.
   CUDA is mandatory — there is no CPU fallback and no mock weights.
3. Per question: schema + question prompt via the tokenizer chat template, greedy
   decode (`do_sample=False`, `max_new_tokens=256`), CUDA-event GPU timing.
4. The first `SELECT`/`WITH` statement is extracted from the raw output, then
   validated: must start with SELECT/WITH, must not contain write/DDL keywords
   (checked with string literals blanked out), must be a single statement.
5. Valid statements run on a `file:...?mode=ro` connection with
   `PRAGMA query_only=ON` and a progress-handler that aborts after 3 s per statement.
   Errors are captured verbatim; nothing is silently dropped.
6. Outputs:
   - `output/answers.jsonl` — one record per question: `id`, `question`, `sql`,
     `results` (columns/rows/row_count/truncated) **or** `execution_error`, `raw`,
     `token_ids`, `execution_status`, `gen_seconds`, `exec_seconds`, `gpu_ms`.
   - `output/run.json` — model/environment config, input hashes, database hash before
     and after (proves read-only access), counts, timings, GPU peak memory,
     per-question status.

## Hard guarantees

- No gold SQL is present in the inputs and none is invented; the agent never writes
  answers on behalf of the model. `answers.jsonl` always contains the model's own
  raw text and token ids.
- Only read-only SQL can reach the database: static validation plus a read-only
  SQLite connection. Failed or rejected queries are recorded, not deleted.
- Every planned question gets a terminal record (ok / error / rejected /
  infrastructure_error).

## Honest limitations

- The task model is a 0.5B instruction model: SQL may be wrong, reference
  non-existent columns or be semantically incorrect. That is application quality,
  not infrastructure failure, and is reported as execution status/errors — this
  program does not claim BIRD scores or gold-level correctness.
- Greedy decoding with a 256-token cap can truncate long queries; truncated/invalid
  output is reported as-is.
- The 3 s per-statement timeout may abort genuinely slow queries; the timeout error is
  archived as a real `execution_error`.
- Result sets are capped at 50 000 rows with a `truncated` flag.
- Timings are real wall/GPU-event measurements from a single run; no ensembles or
  hyper-parameter searches are performed.
