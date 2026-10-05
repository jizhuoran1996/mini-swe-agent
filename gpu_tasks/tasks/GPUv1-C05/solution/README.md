# GPUv1-C05 (debug variant) — animate COCO reference images with Stable Video Diffusion

## What this does

`solution/main.py` drives the **local, pre-provisioned** `StableVideoDiffusionPipeline`
(`/models/stabilityai--stable-video-diffusion-img2vid`, revision
`9cf024d5bfa8f56622af86c884f26a52f6676f2e`) on CUDA in fp16 to animate the genuine
input reference image(s) into short clips.

Frozen protocol (from `input/manifest.json` / `source_spec.json`):

| parameter | value |
|---|---|
| pipeline | `StableVideoDiffusionPipeline` |
| device / dtype | CUDA / float16 |
| frames | 14 |
| resolution | 256 x 256 |
| inference steps | 12 |
| decode_chunk_size | 2 |
| motion_bucket_id | 127 |
| noise_aug_strength | 0.02 |
| fps | 7 |

The clip is **generated** by the diffusion model — the input image is never
simply replicated 14 times. Per-request PNG frames, MP4 clips, contact sheets,
`index.jsonl`, `reference-map.jsonl` and `run.json` are written under `--output`.

## Compatibility shims (why this run works now)

The container pins a `huggingface_hub` older than what the pinned `diffusers`
expects. Importing `diffusers.pipelines.stable_video_diffusion` fails at
import time because the following symbols are missing:

* `huggingface_hub.get_cached_repo_tree`
* `huggingface_hub.errors.CachedRepoTreeNotFoundError`

`solution/main.py` therefore installs **local-only stand-ins** for those
symbols into the respective modules *before* diffusers is ever imported:

* `get_cached_repo_tree` scans `HF_HUB_CACHE` for the requested repo and
  returns the cached file list, or an empty list when nothing is cached.
* `CachedRepoTreeNotFoundError` is a `FileNotFoundError` subclass, injected
  into `huggingface_hub.errors` (and top-level `huggingface_hub` for safety).

Because the loader is used with `local_files_only=True` and a local model
directory, this preserves correctness and — critically — never touches the
network. No packages are upgraded, nothing else is monkey-patched, and the
installed shim names are recorded in `run.json`
(`environment.huggingface_hub_shims`) and printed to `stderr` for auditability.

## Usage

```bash
python solution/main.py --help
python solution/main.py doctor --input input          # inspection only, no model run
python solution/main.py run --input input --output output
python solution/main.py run --input input --output output --seed 2024   # new request batch
```

`doctor` verifies that `input/reference.jpg`, `input/requests.jsonl` and
`input/manifest.json` exist, that their sha256 hashes match `manifest.json`,
that the local model container is complete, that CUDA is usable, that an MP4
writer backend exists, and that `StableVideoDiffusionPipeline` is actually
importable (with the shims applied). It never loads model weights or runs
inference. Exit code `0` = everything available, `78` = something is missing.

`run` performs the real GPU work. It also returns `78` (before touching the
GPU) when any required input, the model container, CUDA or the request file is
missing/unusable, and refuses to substitute mock data.

## Inputs

* `input/reference.jpg` — the genuine COCO reference image shipped with the task.
* `input/requests.jsonl` — one JSON object per line (a JSON array is also
  accepted). Recognised keys: `request_id`/`id`/`name`, `prompt`/`text`/
  `caption`/`motion_prompt`, `image`/`image_path`/`reference_image`/`reference`/
  `image_name` (optional; defaults to `reference.jpg`), and an optional `seed`.
* `input/manifest.json` — hash manifest; checked before any work starts.

If a request names an image that is not present in `input/`, the run falls back
to the declared `input/reference.jpg` and records `image_fallback: true` plus
the requested name in `index.jsonl`, so the substitution is visible rather than
silent.

## Outputs (all under `--output`)

```
output/
  clips/<request_id>.mp4            # generated clip, 14 frames @ 7 fps
  <request_id>/video.mp4            # same clip, per-request directory layout
  frames/<request_id>/frame_000.png ... frame_013.png
  review-contact-sheets/<request_id>.png   # 7x2 grid of the decoded frames
  index.jsonl                       # appended per request (params, seed, timings, checks)
  reference-map.jsonl               # request -> reference image mapping + sha256
  run.json                          # cumulative run records: model ref, params,
                                    # CUDA-synchronised timings, peak memory, failures
```

Every request records `motion_delta` (mean |frame0 - frame13|) and `temporal_std`
as explicit evidence that the output is not a still image and not 14 identical
copies, plus a decode re-check (`video_decode_check`) of the written MP4.
Re-running with a new `input/requests.jsonl` regenerates new media and appends
fresh records; existing files are never reused as an answer.

## Reproducibility / accounting

* Seeds are deterministic: `--seed N` gives request *i* seed `N + i`; without
  `--seed`, a per-request `seed` field is used when present, else `i`.
* Timings are measured with `torch.cuda.synchronize()` around model load,
  inference and video encoding, so they are real device-synchronised times.
* `run.json` stores the model repo/revision, the frozen protocol, input hashes,
  GPU name, peak device memory (`torch.cuda.max_memory_allocated`) and the list
  of installed compatibility shims.

## Honest limitations

* This is the **debug** instance of GPUv1-C05 (`scale: debug_only`), i.e. 14
  frames at 256x256, not the reference-large 720p/129-frame HunyuanVideo-I2V
  workload described in `source_spec.json`; that larger specification is *not*
  claimed as delivered here.
* The task manifest only ships one genuine reference image (`reference.jpg`),
  so the debug workload runs the benchmark requests against that declared
  asset; a request naming a different, absent image is reported via
  `image_fallback` in `index.jsonl` instead of being silently faked.
* No audio track is produced: the frozen protocol describes a silent image-to-video
  animation task, and fabricating audio would be a fake output.
* No CPU fallback and no mock weights: without CUDA or without the local model
  container the run exits with code `78` and only a missing-input report.
* The `huggingface_hub` shims exist purely to bridge the pinned
  `diffusers`/`huggingface_hub` version mismatch in this container; if the
  container ever ships a matching hub, the real symbols are used verbatim.
* MP4 encoding relies on whichever of `imageio-ffmpeg`, `torchvision` or
  OpenCV is present in the container; the backend actually used is recorded in
  `run.json` and `index.jsonl`.
* The container has no network access: everything is loaded with
  `local_files_only=True` from `/models/...`.
