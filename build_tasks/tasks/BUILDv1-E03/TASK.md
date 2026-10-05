# BUILDv1-E03 — 构建 Flink 发行包并验收本地流处理

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"-pl flink-core -am 的完整构建与测试，交付核心 JAR 和独立序列化 consumer。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-E03",
  "project": "Apache Flink",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/apache/flink",
    "acquisition_url": "https://codeload.github.com/apache/flink/tar.gz/cb1e7b5571b06ebe3d79f57030663af3e83aefcd",
    "release_ref": "release-1.20.1",
    "commit": "cb1e7b5571b06ebe3d79f57030663af3e83aefcd",
    "filename": "source.tar.gz",
    "bytes": 40204944,
    "sha256": "82bf43c6fe515df0eab51081b32c97669edf22361ecf8a9861a7e41f242e5c1e",
    "submodules_ready": false
  },
  "scope": "-pl flink-core -am 的完整构建与测试，交付核心 JAR 和独立序列化 consumer。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "dependencies.tar.gz",
      "bytes": 202201505,
      "sha256": "8a910bcc61fc6a26bbf41ff39c29b328cd8267fc7ae60f29c1d87ac847d315e9",
      "preparation_run": "prepare_BUILDv1-E03_1791190959364364116",
      "target_outputs_exported": false
    }
  ]
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
