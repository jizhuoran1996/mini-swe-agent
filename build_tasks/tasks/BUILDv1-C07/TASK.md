# BUILDv1-C07 — 构建 Godot 编辑器与 Linux 导出模板

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"tests=yes editor + 基本 headless consumer；官方 unit/GDScript tests。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C07",
  "project": "Godot",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/godotengine/godot",
    "acquisition_url": "https://codeload.github.com/godotengine/godot/tar.gz/49a5bc7b616bd04689a2c89e89bda41f50241464",
    "release_ref": "4.4.1-stable",
    "commit": "49a5bc7b616bd04689a2c89e89bda41f50241464",
    "filename": "source.tar.gz",
    "bytes": 55261841,
    "sha256": "f9973dcb71887e1e0e2dab51381508cb8e3e9f2d01cd73169c2b1699c2fc0740",
    "submodules_ready": true
  },
  "scope": "tests=yes editor + 基本 headless consumer；官方 unit/GDScript tests。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
