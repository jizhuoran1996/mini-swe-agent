# BUILDv1-D08 — 构建可持久化的 etcd 发布工具包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"构建三个发布工具，执行所列 MVCC 测试并做 put/get 消费者。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D08",
  "project": "etcd",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/etcd-io/etcd",
    "acquisition_url": "https://codeload.github.com/etcd-io/etcd/tar.gz/a17edfd59754d1aed29c2db33520ab9d401326a5",
    "release_ref": "v3.5.21",
    "commit": "a17edfd59754d1aed29c2db33520ab9d401326a5",
    "filename": "source.tar.gz",
    "bytes": 4134535,
    "sha256": "be27f6f50dad496f4fe8e8fe7a357a303b2ba7fe770307c286e104a3ccc1dea9",
    "submodules_ready": true
  },
  "scope": "构建三个发布工具，执行所列 MVCC 测试并做 put/get 消费者。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "dependencies.tar.gz",
      "bytes": 94222382,
      "sha256": "9759b8d5f5c51d2efc7c5b2b818afb1dbdc720f66e7be88dda1c4f0ae758ada4",
      "preparation_run": "prepare_BUILDv1-D08_1791189833379720294",
      "target_outputs_exported": false
    }
  ]
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
