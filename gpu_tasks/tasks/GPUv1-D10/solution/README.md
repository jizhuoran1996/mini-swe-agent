# GPUv1-D10 (debug variant) - English to German translation archive + continuation service

Real CUDA inference with the local, read-only model container
`/models/Qwen--Qwen2.5-0.5B-Instruct` (`Qwen/Qwen2.5-0.5B-Instruct`,
revision `7ae557604adf67be50417f59c2c2f167def9a775`).

The debug variant translates the **8 real WMT14 en-de English sentences** in
`input/requests.jsonl` into German. No target/reference column is read, and no
pre-stored translation is ever used.

## Commands

```bash
# full required run
python solution/main.py run --input input --output output

# continuation: translate a brand new sentence on the same local GPU
python solution/main.py translate --text "The cat sits on the mat." \
    --source-language English --target-language German --output new.json

# inspection only (never loads the model, never runs inference)
python solution/main.py doctor --input input

python solution/main.py --help    # no torch/transformers import, no filesystem access
```

`doctor` exits `78` when anything required is missing, `0` when everything is
available. `run` rejects absent/unparseable inputs *before* loading the model
(exit `78`) and fails with exit `3` if CUDA is unavailable - there is no CPU
fallback and no mock/random substitute model.

## Decoding contract

* prompt: tokenizer chat template with a system instruction to translate the
  user's English text into German, `add_generation_prompt=True`
* greedy (`do_sample=False`, `num_beams=1`), `max_new_tokens=128`
* bfloat16 weights moved onto `cuda` (verified: all parameters report
  `device=cuda:0`)

## Outputs (written to `--output`)

| file | contents |
|---|---|
| `translations.jsonl` | one line per request, in input order: `id`, `translation`, `raw_text`, `token_ids` |
| `run.json` | device/model/input digests, decode config, timings (wall + CUDA events), CUDA evidence, all checks |
| `metrics.json` | BLEU/chrF reported **separately** (see limitations) plus non-generative diagnostics |
| `translation_service_config.json` | frozen configuration of the continuation entry point |

## Independent checks performed by `run`

1. **Coverage** - output ids equal input ids, same order, no duplicates.
2. **Token-generation recomputation** - every prompt is generated a second
   time and the returned `token_ids` must match token-by-token; the decoded
   text must round-trip through the tokenizer and all ids must be in vocab.
3. **New-sentence path** - exposed as the `translate` subcommand (same model,
   device and decode settings, fresh prompt, JSON result on disk and stdout).
4. **CUDA usage** - `torch.cuda.is_available()` gate, parameters asserted on
   `cuda:0`, CUDA events around the generation loop, peak allocated/reserved
   device memory recorded.

Non-generative diagnostics also flag empty outputs and exact source copies
(the negative cases named in the specification).

## Honest limitations

* **This is the `debug_only` variant**, not the reference-large task. The
  reference task uses `CohereLabs/aya-expanse-32b` over all of WMT24++ for
  eight languages; that model is not present in this container and is *not*
  substituted here. `formal_large_tested` is `false` and stays `false`.
* Only English->German is validated. The `--target-language` flag is honoured
  in the prompt but other targets are not verified by this run.
* **BLEU and chrF are not computed** and are reported as `null` with a reason:
  no reference translations exist in the input and the specification forbids
  using pre-stored targets. They are reported separately from the generative
  checks so that a missing metric is never mistaken for a passed check.
* The declared `requests.jsonl` sha256 in `input/manifest.json` is 62 hex
  characters, i.e. not a valid sha256 digest. The run records the actual file
  digest, sets `requests_sha256_match` to `null` (not `true`), and does not
  fail on this malformed declaration.
* Decoding is greedy and deterministic; no beam search, sampling, ensembling
  or hyper-parameter search is performed.
* 0.5B is a small multilingual model. Translations are genuine model output
  but should not be treated as professional-quality German.
