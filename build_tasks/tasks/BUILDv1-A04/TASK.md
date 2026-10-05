# BUILDv1-A04 — 构建并验证 HTTPS 客户端开发包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整 CLI/库及 test1–test3，作为本地 HTTP 调通配置。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A04",
  "project": "curl",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/curl/curl",
    "acquisition_url": "https://codeload.github.com/curl/curl/tar.gz/fdb8a789d2b446b77bd7cdd2eff95f6cbc814cf4",
    "release_ref": "curl-8_14_1",
    "commit": "fdb8a789d2b446b77bd7cdd2eff95f6cbc814cf4",
    "filename": "source.tar.gz",
    "bytes": 3519218,
    "sha256": "64205466b2b9c1fd6fc44a8b765842edd67ed1a3a7df554d68efcf117eca8925",
    "submodules_ready": true
  },
  "scope": "完整 CLI/库及 test1–test3，作为本地 HTTP 调通配置。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
