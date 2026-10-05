# BUILDv1-C09 — 构建栅格与矢量数据开发发行包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"不可禁用核心 raster/vector drivers 加 CLI/SDK 和 test-unit/VRT tests。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C09",
  "project": "GDAL",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/OSGeo/gdal",
    "acquisition_url": "https://codeload.github.com/OSGeo/gdal/tar.gz/ed29baf16d20bccbe331d809e0bafd7afde03360",
    "release_ref": "v3.10.3",
    "commit": "ed29baf16d20bccbe331d809e0bafd7afde03360",
    "filename": "source.tar.gz",
    "bytes": 37481702,
    "sha256": "38bdd906cb4e0bf82b1ea13997f7be9d7794d46e563ccdccc789ec78a4319d42",
    "submodules_ready": true
  },
  "scope": "不可禁用核心 raster/vector drivers 加 CLI/SDK 和 test-unit/VRT tests。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
