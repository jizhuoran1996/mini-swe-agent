# BUILDv1-C08 — 构建 CPU 软件图形栈并验证离屏执行

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"LLVMpipe + EGL CPU 软件库、lp/utility tests 和 EGL consumer。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C08",
  "project": "Mesa",
  "profile": "core",
  "source": {
    "upstream_repo": "https://gitlab.freedesktop.org/mesa/mesa",
    "acquisition_url": "https://archive.mesa3d.org/mesa-25.1.2.tar.xz",
    "release_ref": "mesa-25.1.2",
    "commit": null,
    "filename": "source.tar.xz",
    "bytes": 47001872,
    "sha256": "c29c93fd35119b949a589463d1feb61b4000c0daad04e8d543d7f909f119bd97",
    "submodules_ready": true
  },
  "scope": "LLVMpipe + EGL CPU 软件库、lp/utility tests 和 EGL consumer。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
