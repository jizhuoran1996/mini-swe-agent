# GPUv1-C08 (debug variant) — AudioLDM environmental sound library

Generates 16 kHz mono WAV sound effects with the local `cvssp/audioldm-s-full-v2`
AudioLDM checkpoint using Diffusers' `AudioLDMPipeline` on CUDA in fp16.

## Requirements (provided by the container)

* `/models/cvssp--audioldm-s-full-v2` (read-only model container)
* single CUDA GPU (RTX 5090), PyTorch 2.11, Transformers 5.12, NumPy, Diffusers
* `input/requests.jsonl` (one JSON object per line: prompt text plus an id)

No network access is used: `local_files_only=True` is passed to `from_pretrained`
and the checkpoint is read from the local model directory.

## Usage

```bash
# 1) inspect inputs, model files and dependencies (no model load, no inference)
python solution/main.py doctor --input input

# 2) run the task (must have CUDA)
python solution/main.py run --input input --output output

# 3) later re-run with a brand new requests.jsonl; --seed overrides the seeds
python solution/main.py run --input input --output output --seed 1234
```

`main.py --help`, `main.py run --help` and `main.py doctor --help` print help without
importing torch/diffusers or loading any model.

Exit codes: `0` success, `78` missing input file / dependency / no CUDA,
`1` malformed input or a failed generation contract (empty, silent or non-finite audio).

## Two container-specific fixes

### 1. huggingface_hub / audioLDM import compatibility

Some Diffusers builds ship the (deprecated) AudioLDM pipeline together with a
huggingface_hub version that no longer exports every helper that module imports
(for example `get_cached_repo_tree`).  That produces
`Failed to import diffusers.pipelines.deprecated.audioldm.pipeline_audioldm ...
cannot import name 'get_cached_repo_tree' from 'huggingface_hub'` even though the
pipeline itself is fine for local-directory loading, which never touches repo-tree
caching.

Because installing/upgrading packages is impossible offline, the loader:

1. pre-installs clearly-labelled offline stubs for the known-absent hub helpers
   (`get_cached_repo_tree`, `get_cached_repo_tree_from_hf_cache` and
   `CachedRepoTreeNotFoundError`, in `huggingface_hub`, `huggingface_hub.utils` and
   `huggingface_hub.errors`), but only where the installed hub really lacks them;
2. imports `AudioLDMPipeline` through several candidate module paths
   (`diffusers.pipelines.audioldm[.pipeline_audioldm]`, the deprecated one,
   `diffusers.pipelines`, `diffusers`), plus a cheap filesystem scan of the
   installed `diffusers/pipelines` tree for any other `*audioldm*` module;
3. on any `cannot import name 'X' from 'huggingface_hub...'` error, installs an
   offline stub for exactly that symbol and retries the import (bounded, 30 rounds);
4. never silently continues on any other import error — the collected per-candidate
   errors are reported and the run exits with code 78.

Every stub raises a descriptive `RuntimeError` if it is ever called, so a genuinely
required helper can never be faked; error-class stubs are injected as subclasses of
`RuntimeError`.  The module the pipeline was imported from and every installed shim are
recorded in the log, `config.json` and `run.json`.

### 2. AudioLDMPipeline output shape

`AudioLDMPipeline.__call__` does not return a bare array in this diffusers build: it
returns an `AudioPipelineOutput` dataclass whose `.audios` attribute holds the sampled
waveform (other builds return a tuple or a raw array).  The previous version called
`np.asarray(output, dtype=np.float32)` directly and crashed with
`TypeError: float() argument must be a string or a real number, not 'AudioPipelineOutput'`.

The `extract_waveform()` helper now normalises all of these shapes before conversion:
`AudioPipelineOutput(.audios)`, dict-like outputs (`out["audios"]`), tuples/lists (first
element, unwrapped recursively, including a nested `AudioPipelineOutput`), CUDA tensors
(`.detach().cpu().numpy()`), and numpy arrays.  Only then is it cast to float32 and
flattened, and the empty / non-finite / silent checks run as before.

## Protocol actually executed

* Pipeline: `diffusers.AudioLDMPipeline`
* Weights: `cvssp/audioldm-s-full-v2`, revision `feeb3d14203495a4b6ac0893cbdedb2159b4819c`
  (`/models/cvssp--audioldm-s-full-v2`)
* `torch_dtype=torch.float16` (auto-fallback to `dtype=` when a newer diffusers
  signature rejects `torch_dtype`), device `cuda`
* `audio_length_in_s=4.0` (default; a per-request `audio_length_in_s` field or the
  `--audio-length-in-s` flag override it, and the value used is recorded per item)
* `num_inference_steps=12`, `guidance_scale=2.5`, `num_waveforms_per_prompt=1`
* Output: 16 kHz, 16-bit PCM, mono WAV, one file per request id

## Outputs (in `--output`)

| file | content |
|---|---|
| `sounds/<id>.wav` | generated audio for each request, keyed by its id |
| `index.jsonl` | one record per sound: id, prompt, path, sample rate, duration, samples, seed, steps, guidance, sha256, GPU seconds, peak amplitude |
| `sound-library.jsonl` | identical records under the reference-library name |
| `config.json` | frozen configuration used for this run (incl. pipeline import module and hub shims) |
| `run.json` | input/model references with hashes, params, environment, per-item and total synchronized timings, peak GPU memory |
| `rng_state.pt` | torch CPU/CUDA RNG state plus the seed used per id |
| `audition/index.html` | simple playable page over the generated files |

Every WAV is re-opened with the stdlib `wave` module after writing, and each item is
checked for finiteness and non-silence (peak above 1e-4) before it is indexed; GPU
timings are taken around `torch.cuda.synchronize()` so no asynchronous work is counted
as finished early. Pre-existing files that were overwritten are listed in `run.json`
(`overwrote_pre_existing_files`); nothing from a previous run is reused as an answer.

## Honest limitations

* This is the declared **debug** variant: the smaller publicly available native
  AudioLDM-s checkpoint. It does **not** claim completion of the reference-large
  Clotho/Stable-Audio workload, 44.1 kHz stereo output or 15–30 s durations.
* Output is mono 16 kHz because the frozen protocol says 16 kHz WAV and the pipeline's
  vocoder works at 16 kHz.
* The hub compatibility shims only mask missing *repo-tree/caching* helpers that local
  loading does not use; if a shim were actually required at generation time it raises a
  descriptive error instead of producing bogus audio. If the installed diffusers needs
  a genuinely different (non-hub) API, the per-candidate import errors are reported and
  the run exits non-zero rather than fabricating output.
* fp16 diffusion on a single GPU is deterministic only up to kernel/torch version and
  hardware; the seeds and RNG state are recorded so a run can be reproduced on the same
  stack.
* The checkpoint is used verbatim from the read-only container; its revision string is
  recorded but only `model_index.json` is hashed (not the full weight set).
