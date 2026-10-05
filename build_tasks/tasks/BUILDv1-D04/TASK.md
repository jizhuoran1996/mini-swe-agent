# BUILDv1-D04 — 交付经验证的 RocksDB 嵌入式存储 SDK

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"static_lib + db_basic_test 与静态消费者。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D04",
  "project": "RocksDB",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/facebook/rocksdb",
    "acquisition_url": "https://codeload.github.com/facebook/rocksdb/tar.gz/4b2122578e475cb88aef4dcf152cccd5dbf51060",
    "release_ref": "v10.2.1",
    "commit": "4b2122578e475cb88aef4dcf152cccd5dbf51060",
    "filename": "source.tar.gz",
    "bytes": 13784201,
    "sha256": "23b6a27b8825b94a355fc4c379a7932070c7bd9a1984e621247af5718362ea31",
    "submodules_ready": true
  },
  "scope": "static_lib + db_basic_test 与静态消费者。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
