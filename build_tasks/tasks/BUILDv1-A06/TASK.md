# BUILDv1-A06 — 构建异步 I/O 与进程管理开发包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整库和 timer、spawn_exit_code、threadpool_queue_work_simple 三项测试。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A06",
  "project": "libuv",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/libuv/libuv",
    "acquisition_url": "https://codeload.github.com/libuv/libuv/tar.gz/5152db2cbfeb5582e9c27c5ea1dba2cd9e10759b",
    "release_ref": "v1.51.0",
    "commit": "5152db2cbfeb5582e9c27c5ea1dba2cd9e10759b",
    "filename": "source.tar.gz",
    "bytes": 1353019,
    "sha256": "eeb2cdd529d0de964dccb479afb37427cdf001288786c51babe12c79c9cc8eac",
    "submodules_ready": true
  },
  "scope": "完整库和 timer、spawn_exit_code、threadpool_queue_work_simple 三项测试。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
