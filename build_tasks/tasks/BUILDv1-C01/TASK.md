# BUILDv1-C01 — 构建可安装的 CPU 媒体工具链并通过 FATE

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"标准内建 CPU 工具/库干净构建，运行冻结的核心 FATE 子集。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C01",
  "project": "FFmpeg",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/FFmpeg/FFmpeg",
    "acquisition_url": "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/db69d06eeeab4f46da15030a80d539efb4503ca8",
    "release_ref": "n7.1.1",
    "commit": "db69d06eeeab4f46da15030a80d539efb4503ca8",
    "filename": "source.tar.gz",
    "bytes": 15914259,
    "sha256": "173ba614d8636491106cba08d79db469b5dee4b479388bc4fbcead8ca1fb79b1",
    "submodules_ready": true
  },
  "scope": "标准内建 CPU 工具/库干净构建，运行冻结的核心 FATE 子集。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
