# BUILDv1-B08 — 从源码构建 Go 工具链并交付本机开发环境

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "linux/amd64，CGO_ENABLED=0",
  "tests": "bytes/strings/encoding/json/compress/gzip",
  "deliverable": "完整纯 Go 本机工具链"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B08",
  "project": "Go",
  "profile": "core",
  "source": {
    "upstream_repo": "https://go.googlesource.com/go",
    "acquisition_url": "https://go.dev/dl/go1.24.4.src.tar.gz",
    "release_ref": "go1.24.4",
    "commit": null,
    "filename": "source.tar.gz",
    "bytes": 30788576,
    "sha256": "5a86a83a31f9fa81490b8c5420ac384fd3d95a3e71fba665c7b3f95d1dfef2b4",
    "submodules_ready": true
  },
  "scope": {
    "scope": "linux/amd64，CGO_ENABLED=0",
    "tests": "bytes/strings/encoding/json/compress/gzip",
    "deliverable": "完整纯 Go 本机工具链"
  },
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
