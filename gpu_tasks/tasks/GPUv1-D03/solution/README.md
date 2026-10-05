# GPUv1-D03 (debug variant) - HumanEval function-body completion on CUDA

This directory contains the full implementation for the debug variant of
GPUv1-D03.  The real, larger specification (LongBench RepoBench-P, full 500
contexts, Qwen2.5-Coder-32B-Instruct) is preserved in `source_spec.json` and is
**not** claimed to be completed here.  Per `input/manifest.json` this variant
uses the 8 native HumanEval function prefixes shipped in `input/requests.jsonl`
and the local 0.5B code model at
`/models/Qwen--Qwen2.5-Coder-0.5B-Instruct`.

## Files

* `solution/main.py` - the only entry point.
* `solution/README.md` - this file.
* (produced by `run`) `output/completions.jsonl`, `output/run.json`.

## CLI

```
python solution/main.py --help                         # never loads models
python solution/main.py doctor  --input input          # static pre-flight
python solution/main.py run     --input input --output output
python solution/main.py serve   --port 8123
```

### `doctor`

`doctor --input input` inspects, **without loading the model and without any
inference**:

* `input/requests.jsonl` exists, parses, and has unique ids,
* any file declared in `input/manifest.json` exists and matches its sha256,
* the local model directory contains `config.json`,
* the model directory contains weight shards (`*.safetensors` / `*.bin`),
* the model directory contains tokenizer files,
* the required Python modules `torch`, `transformers`, `numpy`, `fastapi`,
  `uvicorn` are importable,
* `torch.cuda.is_available()` reports True.

Every problem is listed on stderr.  Exit code is **78** if anything is missing
and **0** if all checks pass.

### `run`

For each request in `input/requests.jsonl`:

1. The prompt is rendered with the fixed profile
   `qwen25coder-instruct-codecompletion-v1`: a Qwen chat template with the
   system message stored in `SYSTEM_PROMPT` and the user template
   `USER_TEMPLATE` (placeholder `{prompt}`).
2. A **fresh** greedy generation is performed on CUDA with
   `do_sample=False, num_beams=1, repetition_penalty=1.0, max_new_tokens=256`.
   Because greedy decoding is deterministic argmax, no RNG seeding is needed;
   this is recorded in `run.json`.
3. The raw decoded reply is saved untouched as `raw_generation` together with
   the exact `token_ids`.
4. The reply is normalized (see below) into `completion`, which is intended to
   be concatenated as `prompt + completion`.

The completion JSONL line for each id contains:
`id`, `prompt`, `model_input`, `raw_generation`, `token_ids`, `completion`,
`normalization`, `generation`, `checks`.

`run.json` records the input sha256, model repository / revision / container
path / dtype / device (bf16 on CUDA), prompt template, greedy parameters,
normalization rules, per-problem new-token counts and timings, plus a
`pass_at_1` field which is **null** because the hidden HumanEval unit tests are
not present in this container.  The evaluator measures pass@1 independently.

### `serve`

Starts an HTTP service with

* `GET /health` (aliased at `/healthz`): returns `status: ok` **only after the
  model has been loaded onto CUDA**.  If CUDA is unavailable the model load
  raises and the process exits; the service never reports ready on CPU.
* `POST /complete`: body `{"id": <string|null>, "prompt": <string>}`.  Returns
  the same schema as a line of `completions.jsonl` (minus `model_input`).
  Each call performs a *fresh* greedy CUDA generation; no caching, no stored
  answers.

`SIGTERM` / `SIGINT` trigger uvicorn's graceful shutdown (with a 10 s
graceful timeout) and the `finally` block explicitly drops the model and calls
`torch.cuda.empty_cache()`.

## Hard CUDA contract

`ModelRunner.__init__` calls `_require_cuda(torch)` before anything else.  If
`torch.cuda.is_available()` is False a `RuntimeError` is raised; if a non-CUDA
`--device` is passed a `RuntimeError` is raised.  There is **no CPU fallback**,
**no mock weights** and no random-substitute path.  The first CUDA tensor is
created when the model is moved to `cuda`; every token id in the output comes
from that CUDA forward pass.

## Normalization (profile `v1`)

Stored verbatim inside each record's `normalization.rules`.  Summary:

1. newlines normalized for the *copy* used by the extractor; `raw_generation`
is not modified;
2. a uniform Markdown fence wrapper is dropped;
3. leading/trailing blank lines removed;
4. preferred extraction is `ast` based, trying `standalone`, `prompt+text`,
   `prompt+indented_text`, each time keeping the statements after the docstring
   of the prompt's function (so a restated signature / docstring / imports /
   trailing demo code is removed);
5. if the full candidate does not parse, trailing lines are dropped one at a
   time until it does;
6. docstring-tail fallback;
7. raw-text last-resort fallback, with `normalization.applied.fallback=true`;
8. re-indent uniformly (`textwrap.dedent` then `def indent + 4 spaces`);
9. `prompt + completion` is meant to be compiled/executed as-is.

The standard module-level HumanEval prefixes use 4-space indentation, which
rule 8 reproduces exactly.

## Checks recorded per problem

* `syntax_ok`: `compile(prompt + completion)` succeeds.
* `local_docstring`: `>>>` examples that are part of the *prompt* are executed
  with `doctest`.  This is a self-check only and is **not** the hidden
  HumanEval unit test; those remain in the independent evaluator.

## Notes / limitations

* Debug variant: 0.5B model, 8 native prompts.  The `reference-large` target
  (32B, 500 RepoBench-P contexts) is **not** claimed.
* `pass_at_1` in `run.json` is `null`.  The number reported in
  `counts.local_docstring_examples_passed` must not be mistaken for pass@1.
* Report/package only writes `solution/` and `output/`.
* The service is a genuine CUDA service: readiness requires a real CUDA model
  load, and every `/complete` response carries the raw tokens and grep-able
  provenance from a fresh model forward pass.
* No hyperparameter search and no ensemble; exactly one run configuration
  (`greedy`, `max_new_tokens=256`, frozen template).
