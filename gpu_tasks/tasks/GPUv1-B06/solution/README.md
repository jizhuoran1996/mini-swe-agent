# GPUv1-B06 - Source-native CenterPoint adapter (nuScenes)

Bounded, single-run source-native adapter around MMDetection3D's
`tools/train.py` / `tools/test.py` for the frozen config
`centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py`.
The adapter never fabricates weights, never substitutes a CPU fallback, never
downloads assets, and never reports a blocked input as a solved task.

## Entry points

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run    --input input --output output [--epochs 1 --seed 0 --base-lr F]
python solution/main.py resume --input input --output output [--epochs 1 --seed 0]
```

- `--help` never imports torch/mmengine/mmcv/mmdet3d.
- `doctor --input input` reads `input/manifest.json`, hashes every required file,
  probes the required modules and CUDA, prints a JSON report, and returns
  `0` only if everything is available; otherwise it returns `78` and never
  executes any upstream job.
- `run` requires the admitted inputs, the required modules and CUDA. It builds a
  one-epoch debug config from the frozen source config, launches native
  MMEngine training, produces a `latest.pth` / `epoch_N.pth` checkpoint with
  optimizer and RNG state, then reloads the checkpoint through
  `tools/test.py` to produce a nuScenes-format `detections_nusc.json` plus a
  `scene_index.json` keyed by scene_token and sample timestamp.
- `resume` continues from `output/work/latest.pth` without relabelling.

## Outputs

- `output/configs/centerpoint_debug.py` - effective resolved config (all `_base_` inlined).
- `output/work/{latest,epoch_N}.pth` - CenterPoint checkpoint with optimizer state.
- `output/detections_nusc.json` - `{"results": {sample_token: [boxes...]}}`, translation/rotation/size/velocity/class in nuScenes conventions.
- `output/scene_index.json` - per-scene, per-sample time-ordered query index.
- `output/run.json` - real timings, device name, per-phase wall_s, input SHA256, seed, epochs.
- `output/train.log`, `output/test.log` - verbatim upstream logs.

## Exit codes

- `0` success
- `1` upstream job failed (details in `output/run.json` and logs)
- `4` CUDA required but unavailable
- `78` missing required inputs / modules / resume state

## Honest limitations

- Debug scale only (`native_debug`). Nothing in this repository claims the
  reference large multi-GPU 20-epoch run has been executed.
- The harness must supply the admitted asset tree (`upstream/mmdetection3d`,
  `nuscenes/nuscenes_infos_{train,val}.pkl`, `nuscenes/v1.0-trainval/scene.json`).
  When absent, `doctor` returns 78 and `run`/`resume` refuse to proceed.
- The adapter delegates metric computation to the MMDetection3D nuScenes
  evaluator; the metric numbers in `output/` reflect the mock-free upstream run
  only when the full nuscenes-devkit is present.
- No ensemble, hyperparameter sweep, or multi-seed run is performed.
