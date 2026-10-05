# BUILDv1-C10 — 构建支持 CPU 离屏可视化的科学 SDK

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"Common/Filters/IO 多模块 SDK 与非渲染 C++ test suites。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C10",
  "project": "VTK",
  "profile": "core",
  "source": {
    "upstream_repo": "https://gitlab.kitware.com/vtk/vtk",
    "acquisition_url": "https://codeload.github.com/Kitware/VTK/tar.gz/13acb1a5dd0ad7f7635f2511f44e599733643d06",
    "release_ref": "v9.4.2",
    "commit": "13acb1a5dd0ad7f7635f2511f44e599733643d06",
    "filename": "source.tar.gz",
    "bytes": 45572021,
    "sha256": "10202971c602a646d5f1f45831a1eaa25b99b6f1a0fc733621d41d3d035c2ce2",
    "submodules_ready": true
  },
  "scope": "Common/Filters/IO 多模块 SDK 与非渲染 C++ test suites。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
