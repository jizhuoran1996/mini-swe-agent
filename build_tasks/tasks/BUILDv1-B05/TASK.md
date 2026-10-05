# BUILDv1-B05 — 构建 Node.js 并交付本地事件与国际化运行环境

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "Node + small-icu，固定本地 ICU",
  "tests": "streams 与 message",
  "deliverable": "可使用的 Node runtime"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B05",
  "project": "Node.js",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/nodejs/node",
    "acquisition_url": "https://codeload.github.com/nodejs/node/tar.gz/9774069718d9f80578079d252dddf37ae6fd550d",
    "release_ref": "v22.16.0",
    "commit": "9774069718d9f80578079d252dddf37ae6fd550d",
    "filename": "source.tar.gz",
    "bytes": 123063980,
    "sha256": "e8982dd6338822ff6e231e9551c1b79d098785b6c5e1f9d4b50dcb5b381395f6",
    "submodules_ready": true
  },
  "scope": {
    "scope": "Node + small-icu，固定本地 ICU",
    "tests": "streams 与 message",
    "deliverable": "可使用的 Node runtime"
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
