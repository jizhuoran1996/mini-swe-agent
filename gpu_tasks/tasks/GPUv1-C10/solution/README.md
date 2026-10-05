# GPUv1-C10 (debug variant) - single photo -> reloadable 3D asset

Real COCO photo -> official TripoSR geometry + real decoder-queried vertex
colours -> GLB/PLY + three CPU-shaded preview PNGs + provenance reports.

## Fix for the reported reload-validator crash

### Symptom

Recent runs succeeded up to the exported GLB, which carried `COLOR_0` and the
declared PBR `metallic=0 / roughness=0.5`. The final validator then failed with
an `IndexError` while reporting `vertex_color_count = 4`, and the process
aborted *before* the three previews were rendered.

### Root cause

`mesh.visual.vertex_colors` is not always a per-vertex array. For files that
carry a PBR material, Trimesh builds a `TextureVisuals` whose `vertex_colors`
property delegates to `main_color` - a single RGBA row of shape `(4,)`. The
old code did `vc8[:, :3]` on that row, which raised `IndexError`; `len(vc8)`
returned 4 and was misreported as the vertex count. Per-vertex colours, when
present, actually live in `visual.vertex_attributes["color"]`.

### Fix

1. `get_vertex_colors(mesh)` returns only arrays of shape `(N, 3)` or
   `(N, 4)` with `N == len(mesh.vertices)`. It reads
   `visual.vertex_attributes["color"]` first and only then tries
   `visual.vertex_colors`; `main_color` is never accepted.
2. A new `parse_gltf_accessor()` decodes the glTF `COLOR_0` accessor directly
   out of the GLB binary chunk (respecting `byteOffset` / `byteStride` /
   `componentType` / `type`), so the true per-vertex colours are recovered even
   when Trimesh hides them inside a `TextureVisuals`.
3. `validate_glb_reload()` now checks the file in two independent ways
   (Trimesh reload + raw glTF accessor parse) and reports
   `effective_vertex_color_source` (`trimesh_visual` or `glb_binary_parse`)
   plus `glb_vs_trimesh_color_max_abs_diff` when both are available.  It
   returns success only when the effective colours exist and their count
   exactly equals the vertex count.  No check was weakened; the accessor-level
   verification is strictly stronger.
4. `run` renders the previews only after the reload validator passes, so a
   failure there now surfaces with a full JSON report instead of crashing the
   whole pipeline silently.

Nothing else in the contract changed.

## Other required behaviour

* **Config pre-resolution.** Every `${...}` in
  `/models/stabilityai--TripoSR/config.yaml` is rewritten to a literal
  *before* the DictConfig is constructed; substitutions are logged to
  `index.json.model.config.interpolation_repairs` and
  `run.json.config_interpolation_patches`.
* **Strict 549-key checkpoint load, no substitution.** `model.ckpt` is loaded
  into a tensor state dict; `load_state_dict(strict=False)` collects
  `missing/unexpected` and any non-empty list aborts the run; a
  `strict=True` load follows; every `image_tokenizer.model.*` tensor is then
  compared byte-for-byte against the checkpoint.
* **Offline.** The only network call upstream (DINO `config.json` via
  `hf_hub_download`) is narrowly redirected to `/models/facebook--dino-vitb16/config.json`
  for the four official DINO repo ids; other calls are rejected. The patch
  must fire or the run aborts.
* **No background removal model.** `rembg`/`u2net` are not invoked; the raw
  photo is letterboxed to a grey 512x512 square and the transform is recorded
  in `index.transform`.
* **64^3 isosurface.** CPU `skimage.measure.marching_cubes` is used behind the
  `torchmcubes` API when that package is absent (task allowed); the density
  field itself is still GPU.
* **Real vertex colours.** Attached via trimesh `ColorVisuals`, exported as
  `COLOR_0` in the GLB.
* **Declared material.** GLB JSON chunk patched to a single
  `pbrMetallicRoughness` with `metallicFactor=0.0`, `roughnessFactor=0.5`, and
  every primitive bound to it.
* **`inspect` (fresh process).** `python solution/main.py inspect
  --asset output/asset.glb --output path.json` parses the GLB, recovers the
  actual per-vertex colours (Trimesh OR binary accessor), prints the report on
  stdout and writes it to `--output` unless `-`, echoes failed checks and any
  error to stderr, and returns 0 only when every check passes.

## Outputs (in `output/`)

* `asset.glb` - single mesh, `COLOR_0` vertex colours, pbrMetallicRoughness
  metallic=0.0 roughness=0.5
* `mesh.ply`
* `preview_az030.png`, `preview_az150.png`, `preview_az270.png`
* `index.json` - input sha256, preprocessing transform, model bindings and
  hashes, config interpolation pre-resolution log, HF config-patch evidence,
  checkpoint key counts, strict-load outcome, mesh and material parameters
* `run.json` - CUDA-synchronised stage timings, peak device memory, shim
  status, config interpolation pre-resolution log, HF patch call counters,
  strict load result, truncated error + traceback on failure
* `quality_report.json` - independent topology / appearance summary

## Run

```bash
python solution/main.py doctor  --input input
python solution/main.py run     --input input --output output
python solution/main.py inspect --asset output/asset.glb --output output/inspect.json
```

`main.py --help` never imports torch or transformers.

## Honest limitations

* **debug_only** variant: one photo, one run, 64^3 extraction. It does not
  implement and does not claim the reference-large 1,030-object catalogue.
* Isosurface polygonisation runs on the CPU via `skimage` (task-allowed);
  density field and vertex colours still come from the GPU decoder.
* Background segmentation is off (no network for `rembg`); on a busy raw
  photo reconstruction may include scene content.
* Material metallic/roughness are declared surface defaults; no reflectance is
  inferred and the reports say so.
* Pre-resolution replaces interpolation strings with values already present in
  the file or a documented default. The exact substitution list is recorded in
  `index.json` and `run.json`.
* Previews are CPU renders of the exported mesh, not a hidden-view oracle.
* If strict load fails, the run exits non-zero and dumps mismatching key names
  to `run.json`; there is no partial accept or substitute fallback.
