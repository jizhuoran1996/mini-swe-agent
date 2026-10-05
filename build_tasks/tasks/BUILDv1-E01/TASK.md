# BUILDv1-E01 — 构建 Kafka 发行包并验收事件往返

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"只构建 clients JAR 并运行 RequestResponseTest 与独立序列化 consumer；不声称包含 broker。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-E01",
  "project": "Apache Kafka",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/apache/kafka",
    "acquisition_url": "https://codeload.github.com/apache/kafka/tar.gz/f745dfdcee2b9851204ddbbcd423626ab87294bc",
    "release_ref": "3.9.1",
    "commit": "f745dfdcee2b9851204ddbbcd423626ab87294bc",
    "filename": "source.tar.gz",
    "bytes": 13091937,
    "sha256": "9aa86aa4b739a5b93e9d3fddda15721edfc700ce3f96364f91de120cdca8f87e",
    "submodules_ready": true
  },
  "scope": "只构建 clients JAR 并运行 RequestResponseTest 与独立序列化 consumer；不声称包含 broker。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "dependencies.tar.gz",
      "bytes": 371458653,
      "sha256": "3acb1bf5a36bb96cdd17887199248729dd454d2716ff92277e87df10dac27b96",
      "preparation_run": "prepare_BUILDv1-E01_1791192331378379833",
      "target_outputs_exported": false
    }
  ]
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
