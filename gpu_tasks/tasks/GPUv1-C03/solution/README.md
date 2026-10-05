# GPUv1-C03 (debug) - Canny-controlnet photo re-synthesis

Turn real photos into new layout-preserving assets driven by Canny edges.

## Environment

* Single RTX 5090, CUDA required (fp16).
* Provided: PyTorch 2.11, Transformers 5.12, NumPy, Pillow.
* Models are read-only at:
  * `/models/lllyasviel--sd-controlnet-canny` (revision `7f2f69197050967007f6bbd23ab5e52f0384162a`)
  * `/models/stable-diffusion-v1-5--stable-diffusion-v1-5`
* No network access. Only local assets are used; no mock weights.

## Usage

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output
```

`run` also works on any new input directory that contains its own
`requests.jsonl` plus the referenced photos (fresh-request support).

## Input contract

`<input>/requests.jsonl` - one JSON object per line. Recognised fields:

* `id` / `image_id` / `name` (fallback: line index) - drives `<id>.png` names.
* `image` / `image_path` / `path` / `image_file` - photo path (relative to the
  input dir or `input/images/`). If absent, `input/images/<id>.png` is used.
* `prompt` (preferred) or one of `caption` / `description` / `text`.
* `style_brief` / `style` - appended to the text prompt when present.
* `mask` - **ignored** for this task (noted in the manifest deviations).

## Outputs (under `--output`)

* `control/<id>.png` - 3-channel 512x512 Canny(100, 200) conditioning image.
* `images/<id>.png` - generated 512x512 image (sd-controlnet-canny, fp16, CUDA).
* `index.jsonl` - per request: id, input path, sha256 of the source photo,
  control path, output path, prompt, seed, steps, guidance, conditioning scale.
* `run.json` - device, GPU name, torch/diffusers versions, model paths,
  generation config, per-request seed / input hash / synchronized timing,
  total synchronized seconds and wall time.

## Algorithm

1. Resize source photo to 512x512 (LANCZOS).
2. `cv2.Canny(gray, 100, 200)` -> stacked RGB conditioning image
   (a pure-NumPy Canny with the same thresholds is used if cv2 is absent).
3. `StableDiffusionControlNetPipeline` + `ControlNetModel` (sd-controlnet-canny)
   in fp16 on CUDA, 12 steps, guidance 7.5, `controlnet_conditioning_scale=1.0`.
4. Deterministic per-id seed (`sha256("GPUv1-C03:<id>")[:8]`) stored in
   `index.jsonl` / `run.json` so any request can be replayed exactly.

Timing for each image is measured with `torch.cuda.synchronize()` around the
pipeline call and recorded as `sync_seconds`.

## Doctor

`doctor` inspects the input dir, model dirs and Python dependencies without
loading any model. `ok=false` and exit code `78` mean at least one required
item is missing; `0` means everything required is present. CUDA presence is
reported but not required for `doctor` (it is required for `run`).

## Environment compatibility shim

This container pairs a newer `diffusers` (under `/opt/suite-deps`) with an
older `huggingface_hub` (under `/opt/task-python`).  The diffusers import
path references a handful of `huggingface_hub` names that the installed
version does not export.  Concretely, `diffusers/pipelines/pipeline_utils.py`
does:

```python
from huggingface_hub.errors import CachedRepoTreeNotFoundError
```

which raises `ImportError` because the installed `huggingface_hub.errors`
module does not define `CachedRepoTreeNotFoundError`.

Since package installation is not permitted, `solution/main.py` installs a
small, well-scoped shim (`_ensure_hf_compat()`), executed at module load time
and re-asserted just before importing diffusers:

* `CachedRepoTreeNotFoundError` is defined in both `huggingface_hub` and
  `huggingface_hub.errors`.  It subclasses the local `HfHubHTTPError` /
  `HFHubError` base class (if present) plus `OSError`, so any existing
  downstream `except` clause continues to work.  If a newer `huggingface_hub`
  already provides a real class, the shim reuses it.
* `get_cached_repo_tree` is provided as a local-cache walker over
  `huggingface_hub.scan_cache_dir` (never touches the network).
* Inert placeholders (`DDUFEntry`, `DDUFExportError`, `export_entries_as_dduf`,
  `read_dduf_file`) are also provided for other recent symbols.
* The shim is propagated to any already-imported `huggingface_hub.*`
  submodule that lacks the attribute.

All model loading in this task uses **local directories** (`/models/...`),
so none of these placeholders is ever exercised at runtime; the shim only
lets `from diffusers import ...` resolve.  On a container where the versions
already match, `_ensure_hf_compat()` is a no-op.

## Honest limitations

* This is the **debug_only** variant: it uses SD1.5 + sd-controlnet-canny, not
  the FLUX.1-Canny reference-large pipeline, and makes no claim about the
  unmeasured reference-large workload.
* Only the requests present in `input/requests.jsonl` are processed (two real
  COCO images in this debug pack). No hyper-parameter search, no ensembling.
* The pure-NumPy Canny fallback approximates OpenCV's Canny hysteresis; when
  OpenCV is importable (the normal case) `cv2.Canny` is used directly.
* Seeds are derived deterministically rather than from a global RNG, so results
  are reproducible on the same hardware/driver/library stack.
* If any required file/module is missing, `run` exits with code 78 before
  spawning any model work. It is never counted as a successful run.
* The compatibility shim works around a version skew between the shipped
  diffusers and the installed huggingface_hub; if a future container update
  ships a matching pair, `_ensure_hf_compat()` becomes a no-op.
