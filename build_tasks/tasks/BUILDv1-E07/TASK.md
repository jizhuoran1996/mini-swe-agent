# BUILDv1-E07 — 构建 Rollup 的 JS 与原生解析器分发

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"官方 build:prepare 的 Node native + JS 交付及对应 Node API 测试，不声称含完整 WASM/browser 分发。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-E07",
  "project": "Rollup",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/rollup/rollup",
    "acquisition_url": "https://codeload.github.com/rollup/rollup/tar.gz/02da7efedcf373f0f819b78e3acbe50de05d9a5b",
    "release_ref": "v4.40.2",
    "commit": "02da7efedcf373f0f819b78e3acbe50de05d9a5b",
    "filename": "source.tar.gz",
    "bytes": 2149494,
    "sha256": "c2ee8805d06904ab80f249475f76f24cc3773812dcaa5d5f8cc134a5606c8255",
    "submodules_ready": true
  },
  "scope": "官方 build:prepare 的 Node native + JS 交付及对应 Node API 测试，不声称含完整 WASM/browser 分发。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "dependencies.tar.gz",
      "bytes": 147229993,
      "sha256": "0a4d5aaa047def3ebaf770c7d5de602df0cff877fa5c87068084de4a0e83f337",
      "preparation_run": "prepare_BUILDv1-E07_1791194024283040229",
      "target_outputs_exported": false
    }
  ]
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
