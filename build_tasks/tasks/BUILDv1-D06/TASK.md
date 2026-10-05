# BUILDv1-D06 — 构建可独立链接的 Arrow 列式数据 SDK

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"Arrow core/IPC + IPC read-write test 与消费者。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D06",
  "project": "Apache Arrow",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/apache/arrow",
    "acquisition_url": "https://codeload.github.com/apache/arrow/tar.gz/272715f6df2a042d69881ffa03d5078c58e4b345",
    "release_ref": "apache-arrow-19.0.1",
    "commit": "272715f6df2a042d69881ffa03d5078c58e4b345",
    "filename": "source.tar.gz",
    "bytes": 17583466,
    "sha256": "70c6c8c2736d6edfbe956c8249fc6baca2d11adf5bfc129f981c6f647382bb77",
    "submodules_ready": false
  },
  "scope": "Arrow core/IPC + IPC read-write test 与消费者。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
