# BUILDv1-E06 — 构建 TypeScript 编译器包并验收类型检查

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"build:compiler + 非空官方 compiler test 子集，仍交付完整 compiler 包。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-E06",
  "project": "TypeScript",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/microsoft/TypeScript",
    "acquisition_url": "https://codeload.github.com/microsoft/TypeScript/tar.gz/c63de15a992d37f0d6cec03ac7631872838602cb",
    "release_ref": "v5.9.3",
    "commit": "c63de15a992d37f0d6cec03ac7631872838602cb",
    "filename": "source.tar.gz",
    "bytes": 32924949,
    "sha256": "bfce164d0d86da62a2b79c2585a7e0fc08ff8d15ce9c87748a756de4960531e8",
    "submodules_ready": true
  },
  "scope": "build:compiler + 非空官方 compiler test 子集，仍交付完整 compiler 包。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "dependencies.tar.gz",
      "bytes": 41622478,
      "sha256": "df3e89eb341e9cd5d2923ba4a14492a577a9c6dbac49aa90cae3ef0d700a2720",
      "preparation_run": "prepare_BUILDv1-E06_1791189856630437160",
      "target_outputs_exported": false
    }
  ]
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
