# BUILDv1-D01 — 构建并交付可嵌入应用的 PostgreSQL 工具链

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"默认 server、客户端与 libpq；只运行 core regression。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D01",
  "project": "PostgreSQL",
  "profile": "core",
  "source": {
    "upstream_repo": "https://git.postgresql.org/git/postgresql.git",
    "acquisition_url": "https://ftp.postgresql.org/pub/source/v17.5/postgresql-17.5.tar.bz2",
    "release_ref": "postgresql-17.5",
    "commit": null,
    "filename": "source.tar.bz2",
    "bytes": 21595174,
    "sha256": "fcb7ab38e23b264d1902cb25e6adafb4525a6ebcbd015434aeef9eda80f528d8",
    "submodules_ready": true
  },
  "scope": "默认 server、客户端与 libpq；只运行 core regression。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
