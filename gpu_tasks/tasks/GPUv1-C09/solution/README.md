# GPUv1-C09 (debug variant) - short English speech reusing a reference voice

Generates short WAV files that reuse the voice of the genuine LibriSpeech recording
`input/reference.wav` (with its transcript `input/reference_text.txt`) using the official
`qwen_tts` `Qwen3TTSModel` -- `Qwen/Qwen3-TTS-12Hz-0.6B-Base`, revision
`5d83992436eae1d760afd27aff78a71d676296fc`, mounted read-only at
`/models/Qwen--Qwen3-TTS-12Hz-0.6B-Base`.

## Commands

```bash
python solution/main.py --help                      # prints help, loads nothing
python solution/main.py doctor --input input         # inspect files/deps, exit 78 if anything missing
python solution/main.py run --input input --output output
python solution/main.py run --input input --output output --seed 4242   # later requests, new seed
```

`run` exits `78` when the input contract, the local model or CUDA is missing, `0` on success and
non-zero on a hard failure. A later `run` with a new `input/requests.jsonl` regenerates every
requested utterance from scratch (existing files with the same ID are overwritten, never reused
as answers) and rewrites `index.jsonl` / `run.json`.

## What the run does

1. Verifies `reference.wav`, `reference_text.txt`, `requests.jsonl` (size, SHA-256 against
   `manifest.json` when present, decodability of the WAV, non-empty transcript, parseable requests)
   and that the local model directory has `config.json` plus weight files.
2. Registers three offline compatibility layers before the first `qwen_tts` / `transformers`
   import:
   * `sox` (pysox) is absent, so a compatibility module implements the ordinary pysox audio I/O
     surface (resample/convert/gain/normalize/trim, WAV read/write, file metadata).
   * `pooch` (imported unconditionally by `librosa.util.files`) is absent, so a compatibility
     module implements `os_cache` / `create` plus a `retrieve` that first searches the bundled
     librosa package for the requested resource (mel filters, interval tables and other numerical
     data shipped with librosa) and otherwise raises a loud error naming the requested resource,
     so nothing silently pretends to have downloaded anything.
   * `transformers` (from `/opt/qwen-tts-deps/transformers`) pins
     `huggingface-hub>=0.34.0,<1.0`, while the container ships `huggingface-hub==1.33.0`; the pin
     is enforced inside `transformers/dependency_versions_check.py` at import time, before any
     code we control runs. `main.py` therefore patches `importlib.metadata.version` so that the
     *reported* metadata for the single distribution name `huggingface-hub` is a value inside the
     pin. All other lookups pass straight through to the installed function, and the genuine real
     version string is preserved untouched in the report. No other package's version is altered.
   
   Every real module is used untouched when it is importable and already satisfies its pin. Any
   shim symbol actually exercised by upstream code is recorded, along with installation state and
   the real vs. reported huggingface-hub versions, in `doctor` output and in `run.json` under
   `compatibility`.
3. Requires `torch.cuda.is_available()`; there is no CPU fallback for generation.
4. Loads `Qwen3TTSModel.from_pretrained(..., device_map="cuda:0", dtype=torch.bfloat16)` and calls
   `generate_voice_clone(text=..., language=..., ref_audio=<reference.wav>, ref_text=<transcript>,
   x_vector_only_mode=False)` for every request. Argument names are inspected against the real
   signature, so the exact official spelling is used and recorded per request.
5. Writes each waveform as PCM-16 WAV at the model's native sample rate, reads it back and asserts
   it is decodable, finite and non-silent; a silent or non-finite result is a hard error, not a
   delivered answer.
6. Writes `output/index.jsonl` (one record per ID) and `output/run.json` (inputs with hashes, model
   reference, parameters, real GPU-synchronised timings, actual durations, peak CUDA memory,
   compatibility notes) plus `output/rng_state.pt`.

## Outputs

```
output/speech/<id>.wav      generated speech, model-native sample rate
output/index.jsonl          per-ID: text, language, wav, sample rate, samples, duration, sha256, params
output/run.json             inputs/model/params/timings/memory/compatibility/verification
output/rng_state.pt         torch + CUDA RNG states for the recorded seed
```

## Honest limitations

- **Debug scale only.** This run covers exactly the requests present in `input/requests.jsonl`
  (three new English texts in this frozen variant). It is not the 3,000-utterance Seed-TTS
  bilingual reference workload and makes no claim about it.
- **Requires the real environment.** `qwen_tts` must be importable, the 0.6B Base checkpoint must
  exist at the given path, and a CUDA device must be visible. `doctor` reports every missing item
  and exits 78 rather than substituting another TTS backend, random audio, silence or CPU
  inference.
- **Version / dependency mismatch in this container.** `transformers` pins
  `huggingface-hub>=0.34.0,<1.0` but the image ships `huggingface-hub==1.33.0`, and no package
  installation is allowed. `main.py` therefore patches `importlib.metadata.version` only for the
  `huggingface-hub` distribution name, and only after confirming the installed value is outside
  the accepted range. The real value is recorded in `run.json` / `doctor` under
  `compatibility.huggingface_hub_version.real_version` so the fix is fully auditable. If the real
  library's behaviour later diverges from the APIs transformers actually calls, the run will fail
  loudly rather than silently produce substitute audio.
- **pysox and pooch are absent in this container.** `main.py` registers local compatibility
  modules for both import names (as described above) before importing `qwen_tts`. The
  compatibility layers are deliberately narrow: they implement the ordinary operations actually
  used (WAV I/O, resample/gain/normalize/trim for pysox; cache directory plus bundle lookup for
  pooch) and fail loudly, naming the exact symbol and requested resource, if the upstream code
  tries anything they do not cover.
- **No quality tuning.** Decoding uses the model's own defaults and a fixed seed; nothing was tuned,
  no ensembles are produced, and WER/speaker-similarity scoring is left to the independent oracle.
- **No network access.** All assets come from `input/` and `/models/`; nothing is downloaded.
- **Reference reuse only.** The reference recording is used as conditioning for every request; it
  is never copied into the output as an answer, and only the frozen authorised benchmark asset is
  used.
