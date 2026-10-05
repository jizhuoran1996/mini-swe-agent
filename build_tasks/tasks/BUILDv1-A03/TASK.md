# BUILDv1-A03 — 构建多格式归档工具和开发包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整库及 bsdtar，使用冻结的 tar/zip 与基础压缩依赖。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A03",
  "project": "libarchive",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/libarchive/libarchive",
    "acquisition_url": "https://codeload.github.com/libarchive/libarchive/tar.gz/9525f90ca4bd14c7b335e2f8c84a4607b0af6bdf",
    "release_ref": "v3.8.1",
    "commit": "9525f90ca4bd14c7b335e2f8c84a4607b0af6bdf",
    "filename": "source.tar.gz",
    "bytes": 5920582,
    "sha256": "944db9ab58a3cbdb5d947db4f04a3cc15f83b3147fcf7830ada592ba8d4a102c",
    "submodules_ready": true
  },
  "scope": "完整库及 bsdtar，使用冻结的 tar/zip 与基础压缩依赖。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
