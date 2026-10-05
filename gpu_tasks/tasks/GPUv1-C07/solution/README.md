# GPUv1-C07 (debug variant) - short text-to-music assets

Frozen instance: **facebook/musicgen-small**, revision
`4c8334b02c6ec4e8664a91979669a501ec497792`, pre-staged read-only at
`/models/facebook--musicgen-small`.

This is the **debug** variant only. The original `reference-large` workload
(melody-conditioned `musicgen-melody-large` + MusicCaps balanced subset) is
**not** claimed, not downloaded and not approximated.

## Protocol implemented

| Item | Value |
| --- | --- |
| API | `AutoProcessor` + `MusicgenForConditionalGeneration` (official Transformers) |
| Conditioning | **text only** - no melody / chroma conditioning is offered or faked |
| Decoding | greedy (`do_sample=False`) with classifier-free guidance (default 3.0) |
| Length | 4 s per request = 200 audio-code tokens (50 codec frames/s) |
| Output | 32 kHz, mono, 16-bit PCM WAV per request id |
| Device | CUDA mandatory - the run aborts if `torch.cuda.is_available()` is False |

## Environment workaround: cuDNN mismatch

The container's bundled PyTorch was compiled against cuDNN `(9, 19, 0)` while
the runtime `LD_LIBRARY_PATH` supplies `(9, 17, 1)`. This is detected by
`torch.backends.cudnn.is_acceptable(...)` the first time an `nn.RNN` (the
MusicGen decoder LSTM) is moved to CUDA, i.e. inside `model.to('cuda')`.

`main.py` therefore sets `torch.backends.cudnn.enabled = False` **before** the
model is loaded. With the cuDNN backend disabled, `_cudnn_is_acceptable`
short-circuits to `False`, the version check is never reached, and all
convolutions (EnCodec encoder/decoder) and the LSTM decoder use their regular
CUDA kernels. Compute is still on CUDA - this is a dispatch change, not a CPU
fallback. The status is recorded in `run.json`
(`environment.cudnn_backend_disabled_for_run = true`).

## Commands

```bash
# Help (does not import torch/transformers, does not load any model)
python solution/main.py --help
python solution/main.py run --help
python solution/main.py doctor --help

# Non-executing prerequisite inspection (inputs, model files, deps, CUDA)
python solution/main.py doctor --input input
#  -> exit 0 when everything is available, 78 when anything is missing

# Real generation (one run, no hyper-parameter search, no ensemble)
python solution/main.py run --input input --output output --seed 0
```

`--seed` overrides the RNG seed for follow-up runs with a new
`input/requests.jsonl`. `--dtype` accepts `float32` (default), `float16`,
`bfloat16`; `--model` points at a different local checkout of the same
checkpoint. No other knobs exist and none are searched.

## Outputs (written only under `output/`)

```
output/
  music/<asset_id>.wav    32 kHz mono WAV, one per request id
  index.jsonl             one JSON object per asset (prompt, params, duration,
                          sha256, bytes, peak, rms, GPU-synced generate time)
  run.json                input+model references and hashes, parameters,
                          environment (incl. cuDNN state), per-item
                          GPU-synchronized timings, peak device memory,
                          and the full item list
```

A WAV is only accepted after it has been written and re-read with the stdlib
`wave` module: channel count, sample rate, frame count and non-zero content are
re-verified. Samples must be finite and non-silent or the run fails.

## Reruns

Every `run` regenerates audio from the model for **every** record in the
supplied `requests.jsonl`. Existing files in `output/` are never reused as the
answer, so a fresh `requests.jsonl` produces fresh media. Output files with a
colliding id are overwritten; ids inside one run are de-duplicated with a
numeric suffix.

## Honest limitations

* `musicgen-small` is a small text-to-music variant; prompt adherence and
  musicality are correspondingly modest, and lyrics are not reproduced.
* Greedy decoding with guidance is deterministic for a fixed model revision and
  dtype; `--seed` is recorded and applied but does not change greedy output.
* Quality is judged by an independent acceptance report; this code makes no
  quality claim and performs no tuning, no ensembling and no prompt search.
* Disabling the cuDNN backend is required here only because of the frozen
  container's bundled/runtime version mismatch; it does not change the model
  weights, generation settings or CUDA execution.
* No network access, no package installation and no CPU fallback are used. If
  the local checkpoint is absent or CUDA is unavailable, the run exits with
  code 78 and produces no media.
* WAV writing/reading uses the Python standard library `wave` module (plus
  NumPy) so it works without optional audio packages.
