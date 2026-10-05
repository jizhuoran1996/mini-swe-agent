# BUILDv1-E02 — 构建 Spark SQL 发行包并交付本地分析程序

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"官方 -pl 子模块构建 core 及其 reactor 依赖并运行 DAGSchedulerSuite；交付 core JAR 和本地 RDD consumer。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-E02",
  "project": "Apache Spark",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/apache/spark",
    "acquisition_url": "https://codeload.github.com/apache/spark/tar.gz/ed00d046951a7ecda6429accd3b9c5b2dc792b65",
    "release_ref": "v3.5.7",
    "commit": "ed00d046951a7ecda6429accd3b9c5b2dc792b65",
    "filename": "source.tar.gz",
    "bytes": 34481233,
    "sha256": "c310db387f7db1f8e8282bea351b884e995f5b68eb47658927d2052cd76e3e9f",
    "submodules_ready": true
  },
  "scope": "官方 -pl 子模块构建 core 及其 reactor 依赖并运行 DAGSchedulerSuite；交付 core JAR 和本地 RDD consumer。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
