# GPUv1-B07 — Cylinder3D SemanticKITTI source-native adapter

Source-native wrapper around the official Cylinder3D single-scan training entry
(`upstream/Cylinder3D/train_cylinder_asym.py`) for SemanticKITTI point-level
semantic segmentation.

## Entry points

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output
python solution/main.py resume --input input --output output
```

- `doctor` inspects, without loading any model:
  - required files declared in `input/manifest.json`
  - required python modules (`spconv`, `torch_scatter`, `yaml`)
  - `torch.cuda.is_available()` and the CUDA device name
  - exits `0` if everything is present, `78` if anything is missing.
- `run` / `resume` re-check the same gate at start.  When anything is missing
they write `output/run.json` with `status="blocked"` and exit `78`; when CUDA is
not available they exit `1`.  No fake labels, mock weights or CPU fallbacks are
produced.

## What `run` actually does

1. Validates the gate, requires a live CUDA device, seeds torch `(0)`.
2. Copies the source config into `output/config/semantickitti.yaml`, then derives
   a **debug** config `output/config/semantickitti_debug.yaml` that:
   - keeps **every model/optimizer/scheduler hyperparameter** from the source yaml,
   - restricts the sequence list to the declared debug scope: a single source
     train sequence (`00`) and validation sequence `08`,
   - shrinks the schedule to a single epoch (or ≤500 iters) since we are only
     validating sparse operators, the label map and output alignment,
   - redirects `save_path` / `data_root` into `output/` and `input/SemanticKITTI/`.
3. Invokes the **source training entry** as a subprocess in the upstream folder:
   `python upstream/Cylinder3D/train_cylinder_asym.py -y <debug.yaml> -n gpu_b07_debug`
   The upstream code performs its own real gradient updates; we never touch the
   optimizer from here.
4. Locates the produced checkpoint (prefers `best*`), records its SHA256 and
   size in `output/run.json`.
5. Runs per-point inference on sequence `08` via the emitted helper
   `output/infer_cylinder3d.py`:
   - re-uses the source model class (`network.Cylinder3D.Cylinder3D`),
   - builds cylindrical voxel indices from the same grid configuration,
   - returns one label per **original** scan point (in the original scan
     order) via the point→voxel index,
   - writes `output/sequences/08/predictions/*.label` (uint32 train ids).
6. Computes the distance-stratified mIoU/IoU report by re-mapping the raw
   SemanticKITTI labels through the official learning map and comparing only on
   *annotated* points (unlabeled class excluded), and writes
   `output/reports/distance_stratified.json`.

## Deliverables

- `output/ckpt/*.pth` — checkpoint produced by upstream training
- `output/config/*.yaml` — frozen source + debug configs (SHA256 in run.json)
- `output/label_map.json` — official learning map + inverse map + class names
- `output/sequences/08/predictions/*.label` — one file per scan, one uint32 per
  original point, in the original scan order
- `output/reports/distance_stratified.json` — per-class IoU and mIoU per radial
  distance bin `[0,20) / [20,40) / [40,60) / [60,80) / [80,∞)`
- `output/run.json` — status, timings, device, checkpoint/config hashes,
  prediction counts and any blocking report

## Continuation (reload from a checkpoint)

`output/infer_cylinder3d.py` is a standalone script.  To run inference on any
other sequence / split from a saved model:

```
python output/infer_cylinder3d.py \
    --upstream input/upstream/Cylinder3D \
    --config  output/config/semantickitti_debug.yaml \
    --ckpt    output/ckpt/<best>.pth \
    --data-root input/SemanticKITTI \
    --sequence 11 \
    --out-dir  output/sequences/11/predictions \
    --map-json output/label_map.json
```

Processed scan IDs are the `.label` file stems; they match the input `.bin`
stems exactly, so the traceability of previously processed scans is preserved.

## Environment this adapter was written against

- CUDA-capable single GPU, `spconv` + `torch_scatter` matching the source
- `python` with `torch`, `numpy`, `yaml` present
- Read-only `input/`, writable `solution/` and `output/`

## Honest limitations

- **Assets were not mounted on the authoring host** (`input/manifest.json`
  declares `assets_ready=false`).  Therefore:
  - the adapter was not executed end-to-end here,
  - `doctor` correctly reports the missing assets and exits `78`,
  - **debug pass is not a reference-scale pass**; the frozen `reference_large`
    profile (full train set + full seq 08 at source schedule) remains
    unmeasured,
  - no checkpoint, prediction file or mIoU number has been produced here.
- The inference helper attempts a small set of well-known import paths for the
  Cylinder3D model class and for the forward signature.  If the specific
  upstream revision uses a different forward contract, the helper will exit
  non-zero with a clear message and `output/run.json` records `status="infer_failed"`.
- `distance_stratified.json` uses the standard SemanticKITTI learning map; minor
  numeric differences vs `semantic-kitti-api` are possible (bins are the same 5
  ranges used in the Cylinder3D paper).
- The wrapper does not perform hyperparameter search or ensembling; it invokes
  the source schedule once as declared.
