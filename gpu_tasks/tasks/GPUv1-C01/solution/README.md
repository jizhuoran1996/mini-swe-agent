# GPUv1-C01 debug variant

Real text-to-image asset-library generation using the **trained distilled**
Stable Diffusion checkpoint `segmind/tiny-sd` (`cad0bd7495fa6c4bcca01b19a723dc91627fe84f`)
from the read-only container path `/models/segmind--tiny-sd`.

This is a debug-scale run. It does **not** claim the reference-large
(5,000 x 1024px SDXL) workload, and it does not claim an official MLPerf
submission.

## Environment

* Single CUDA GPU (target: RTX 5090), CUDA **required**.
* PyTorch 2.11, Transformers 5.12, diffusers, NumPy, Pillow provided.
* FP16 weights on CUDA, 256x256, 12 inference steps, `guidance_scale=7.5`.
* Per-request seed from `requests.jsonl`; deterministic via a CUDA generator.

No CPU fallback, no random-noise placeholder, no copied COCO originals.

### huggingface_hub compatibility shim

The frozen image ships a `huggingface_hub` that predates symbols imported at
diffusers module-load time. Missing symbols observed so far:

* `huggingface_hub.get_cached_repo_tree`
* `huggingface_hub.errors.CachedRepoTreeNotFoundError`

Either one aborts the whole `diffusers.pipelines.stable_diffusion.*` import
graph with an `ImportError`. `main.py` therefore runs
`_install_huggingface_hub_shim()` at module import (and again inside
`load_pipeline` / `do_doctor`) *before* diffusers is imported. The shim:

* creates `CachedRepoTreeNotFoundError` (subclassing the closest available
  hub error class) and installs it on `huggingface_hub`, `huggingface_hub.errors`
  and, if importable, `huggingface_hub.utils` / `huggingface_hub.hf_api`;
* attaches a best-effort `get_cached_repo_tree` that forwards to
  `HfApi.list_repo_tree`.

Both shims are inert for a local-path load (`local_files_only=True`): nothing
is downloaded and the real `segmind/tiny-sd` weights from
`/models/segmind--tiny-sd` are used. The shim only repairs the import graph.

## Usage

```
python solution/main.py --help
python solution/main.py doctor   --input input
python solution/main.py run      --input input --output output
python solution/main.py generate --prompt "a red barn in a field" --seed 42 --output out/barn.png
```

`doctor` performs a static inspection only (input files, model directory,
torch/CUDA availability, dependencies). It exits `78` (EX_CONFIG) if anything
is missing and `0` otherwise. It never loads the model or runs inference.

`run` reads `input/requests.jsonl`, generates one genuine image per request on
the GPU, writes `output/images/<id>.png`, an `output/index.jsonl` asset index
(one record per image with id / prompt / seed / relative image path / frozen
parameters) and `output/run.json` with synchronized wall timings and GPU name.

`generate` is a fresh single-request entry point. It loads the model itself
and does not depend on prior outputs of `run`.

## Output contract

```
output/
  images/<id>.png         one decodable PNG per request id
  index.jsonl             id, prompt, seed, image, parameters
  run.json                config + real GPU wall timings
```

## Honest limitations

* Debug scale only: number of images equals the number of lines in the
  provided `requests.jsonl` (four benign designer-authored requests in the
  shipped input).
* `tiny-sd` is a small distilled model; per-image visual quality is
  intentionally not the formal-large quality bar.
* The `huggingface_hub` shim above papers over an image-level version skew;
  it is inert for local-path loading but should be removed once the container
  pins compatible `diffusers`/`huggingface_hub` versions.
* Bit-exactness across different GPUs/CUDA versions is not guaranteed; seeds
  are fixed to give tolerance-bounded replay on the same stack.
* The formal reference-large spec (SDXL, 5,000 COCO 2014 samples, 1024px) is
  archived in `input/source_spec.json` and is **not** executed here.
