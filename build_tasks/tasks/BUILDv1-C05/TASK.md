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
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "opencv-testdata.tar.gz",
      "sha256": "4dd6dc35a2c3758d85cee88e6df33f8ba5478ce9381adc06bcdbb431f632d22d",
      "bytes": 300488275,
      "target_outputs_exported": false,
      "destination": "/workspace/cache/opencv_extra/testdata"
    }
  ],
  "opencv_official_testdata": {
    "repository": "https://github.com/opencv/opencv_extra",
    "release_ref": "4.11.0",
    "commit": "a74cf6bae7fd75d91282b877c559168b3a62148a",
    "archive_url": "https://codeload.github.com/opencv/opencv_extra/tar.gz/a74cf6bae7fd75d91282b877c559168b3a62148a",
    "archive_sha256": "44955b42abc411f2bb8ebbe31835040049c82b2924dd967b0debde2fe06be492",
    "selection": "testdata/cv",
    "path": "/workspace/cache/opencv_extra/testdata"
  }
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
