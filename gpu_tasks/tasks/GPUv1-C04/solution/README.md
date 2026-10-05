# GPUv1-C04 (debug variant)

Text-to-video asset library generator using the frozen local model
`damo-vilab/text-to-video-ms-1.7b` (revision `8227dddca75a8561bf858d604cc5dae52b954d01`)
at `/models/damo-vilab--text-to-video-ms-1.7b`.

## Environment

- Single CUDA GPU (test target: RTX 5090). Runs under PyTorch 2.11 +
  Transformers 5.12 + Diffusers + NumPy + imageio (with imageio-ffmpeg).
- fp16 on CUDA. There is **no CPU fallback**: if CUDA is not available the
  `run` subcommand raises and exits non-zero.
- No network access is required or attempted. Model is loaded from the local
  read-only path with `local_files_only=True`.

### huggingface_hub compatibility shims

The runtime ships an older `huggingface_hub` than the diffusers copy installed
at `/opt/suite-deps` expects. Two upstream symbols are missing and are shimmed
in-memory (read-only, best-effort) *before* `diffusers` is imported:

1. `huggingface_hub.errors.CachedRepoTreeNotFoundError` — imported at module
   load time by `diffusers/pipelines/pipeline_utils.py`. The shim defines a
   trivial `Exception` subclass under that name.
2. `huggingface_hub.get_cached_repo_tree` — a generator-backed best-effort
   wrapper over `huggingface_hub.scan_cache_dir`.

Both shims only affect cached-repo enumeration. The actual model load uses an
absolute local path and never calls them.

## Fixed protocol

| Item | Value |
| --- | --- |
| Pipeline | `TextToVideoSDPipeline` |
| Precision | `fp16` (CUDA) |
| Resolution | 256 x 256 |
| Frames | 16 |
| Denoise steps | 12 |
| Guidance scale | 7.5 |
| FPS (container) | 8 |

## Frame conversion (fix)

`TextToVideoSDPipeline` returns frames as `float32` NumPy arrays with values
in `[0, 1]`. The previous revision cast those directly with `.astype(uint8)`,
which truncates every value below `1.0` to `0` and produced an all-black
video (`content_nonzero=False`). The corrected conversion in
`_to_uint8_image`:

1. validates every value is finite (`np.isfinite`),
2. clips to `[0, 1]`,
3. multiplies by `255.0` and rounds with `np.rint`,
4. casts to `uint8`.

Inputs that are *already* `uint8` are passed through untouched — they are
never rescaled. Non-`uint8` integer inputs are only scaled when their max is
`<= 1`, otherwise they are treated as `[0, 255]`.

After conversion the code computes the per-frame pixel standard deviation; if
any frame has std `<= 1.0` (or non-finite values) the run raises
`RuntimeError` and refuses to write the clip rather than emit a black video.

## Usage

```
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output
python solution/main.py run    --input input --output output --seed 1234
```

`main.py --help` prints the parser help only; it never imports torch/diffusers
or loads the model.

### Seeds

- If `--seed N` is passed, scene `i` uses `N + i`.
- Otherwise the per-request `seed` field from `input/requests.jsonl` is honored
  (`2026` in the supplied input); a fallback of `2026` is used only if the
  request omits the field. This is what the audit's "honor request seed 2026
  unless `--seed` explicitly overrides" rule requires.

### `doctor`

Inspects the exact required items and prints each missing one:

- `input/requests.jsonl` (must parse as JSONL of objects)
- `input/manifest.json`
- model directory + `model_index.json`
- imports `torch`, `diffusers`, `transformers`, `numpy`, `imageio`, `PIL`
- `torch.cuda.is_available()`
- the actual `TextToVideoSDPipeline` symbol (with the hub shims applied)

Returns `78` (`EX_CONFIG`) if anything is missing, `0` otherwise.

### `run`

For every request line, produces:

```
output/videos/<scene_id>.mp4         # H.264 mp4, 16 frames @ 8 fps
output/frames/<scene_id>/frame_XXXX.png
output/index.jsonl                   # one JSON record per clip
output/run.json                      # full run record
```

`index.jsonl` records per-scene `frame_stats` (`min_std`, `per_frame_std`,
`all_finite`), `content_nonzero`, per-scene `generation_seconds_sync`, and the
`decode_check` (frames decoded from the mp4).

## Decode / integrity verification

After writing each mp4 the file is re-opened with `imageio.get_reader` and
must decode back to exactly 16 frames for `decode_check.decodable` to be
`true`. The decoder's mean/std are also recorded, and a separate per-frame
std check operates on the exported PIL images before any output is accepted.

## Known limitations

- Output resolution is 256x256 / 16 frames per the frozen debug protocol; this
  is not the reference-large (720p/81-frame) asset library and we do not claim
  reference-large completion.
- Generation quality is whatever the native pipeline produces with 12 steps;
  no prompt expansion, refinement, ensembling or hyperparameter search is
  used (per spec).
- mp4 encoding relies on `imageio-ffmpeg` (used by
  `diffusers.utils.export_to_video`). If the backend binary is missing `doctor`
  only checks the Python package; `run` will fail loudly at export time.
- The `huggingface_hub` shims are scoped to `CachedRepoTreeNotFoundError` and
  `get_cached_repo_tree`. If a future runtime pulls in additional missing
  symbols from the same module family, the loader will surface the exact
  missing name rather than silently degrade.
