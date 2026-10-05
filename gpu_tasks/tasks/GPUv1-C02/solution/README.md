# GPUv1-C02 solution

Usage:
  python solution/main.py --help
  python solution/main.py doctor --input input
  python solution/main.py run --input input --output output

The run command reads input/requests.jsonl, loads /models/stable-diffusion-v1-5--stable-diffusion-inpainting with StableDiffusionInpaintPipeline in fp16 on CUDA, uses 512x512, 12 steps and guidance scale 7.5. White mask areas are generated; black areas are composited from the original input pixel-for-pixel. Outputs are written under output/: images/{id}.png, index.jsonl, run.json, config.json.

Compatibility: the installed diffusers build imports `CachedRepoTreeNotFoundError` from `huggingface_hub.errors` and `get_cached_repo_tree` from `huggingface_hub`, but the installed huggingface_hub in this container exports neither. Importing `diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion_inpaint` therefore fails at module load. The solution installs a local shim at module import time that (1) defines `CachedRepoTreeNotFoundError` as an Exception subclass and injects it into `huggingface_hub.errors`, `huggingface_hub`, `huggingface_hub.hf_api` and `huggingface_hub._snapshot_download`; and (2) defines `get_cached_repo_tree` implemented on top of `huggingface_hub.scan_cache_dir` and injects it into the same modules. All shims are no-ops when the target symbol already exists, so they do not override a real, newer huggingface_hub.

Fresh requests: the same run entry processes any valid requests.jsonl in the given input directory. Seed replay: each request uses its seed field if present, otherwise --seed default 0, and seeds are recorded in index.jsonl and run.json for deterministic replay.

Doctor checks input files, request image/mask references, Python dependencies, CUDA availability, huggingface_hub shim status (get_cached_repo_tree and CachedRepoTreeNotFoundError), and the local model snapshot. It exits 78 if any item is missing and 0 if available. It does not load or run the model.

Limitations: no network access, no package installation, no CPU fallback, no mock weights. This is inference-only; no optimizer or training state is produced. The model snapshot and COCO/designer inputs must already be present. The script does not search host files or hidden evaluators.
