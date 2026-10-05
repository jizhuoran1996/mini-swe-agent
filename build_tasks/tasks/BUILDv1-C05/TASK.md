# BUILDv1-C05 — 构建可复用的 CPU 视觉开发工具包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"core/imgproc/imgcodecs/ts 的完整源码构建及相应 accuracy tests。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C05",
  "project": "OpenCV",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/opencv/opencv",
    "acquisition_url": "https://codeload.github.com/opencv/opencv/tar.gz/31b0eeea0b44b370fd0712312df4214d4ae1b158",
    "release_ref": "4.11.0",
    "commit": "31b0eeea0b44b370fd0712312df4214d4ae1b158",
    "filename": "source.tar.gz",
    "bytes": 95080706,
    "sha256": "bb15d5c85bab38c1377c0c7dd7ff201b078bcdb41cc4ff9f85ac61aa56b5f631",
    "submodules_ready": true
  },
  "scope": "core/imgproc/imgcodecs/ts 的完整源码构建及相应 accuracy tests。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
