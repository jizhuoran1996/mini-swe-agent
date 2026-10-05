# BUILDv1-D03 — 构建可持久化的 Redis TLS 安装包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"不启用 TLS 的 core build，运行官方 string 单元并验证普通本地客户端。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D03",
  "project": "Redis",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/redis/redis",
    "acquisition_url": "https://codeload.github.com/redis/redis/tar.gz/7e0f53393290f7c1f35596117b67748efad16580",
    "release_ref": "7.4.5",
    "commit": "7e0f53393290f7c1f35596117b67748efad16580",
    "filename": "source.tar.gz",
    "bytes": 3577943,
    "sha256": "38f195082153b29e17f8df750c6a6b341414cdc915e05c0a3cb183c02de745b8",
    "submodules_ready": true
  },
  "scope": "不启用 TLS 的 core build，运行官方 string 单元并验证普通本地客户端。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
