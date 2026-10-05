# BUILDv1-D05 — 构建带 JSON 与 Parquet 的 DuckDB 分析 SDK

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"core/CLI + [capi]，只处理 SQL 表。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D05",
  "project": "DuckDB",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/duckdb/duckdb",
    "acquisition_url": "https://codeload.github.com/duckdb/duckdb/tar.gz/d1dc88f950d456d72493df452dabdcd13aa413dd",
    "release_ref": "v1.4.3",
    "commit": "d1dc88f950d456d72493df452dabdcd13aa413dd",
    "filename": "source.tar.gz",
    "bytes": 98410341,
    "sha256": "7511e1f509ce9c10a95c0ae58bc4551d4b015b1dc5664f4537b2f6e120c4c91f",
    "submodules_ready": true
  },
  "scope": "core/CLI + [capi]，只处理 SQL 表。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
