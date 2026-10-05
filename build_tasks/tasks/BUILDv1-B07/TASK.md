# BUILDv1-B07 — 构建 PHP 并验收 CLI 与 SQLite 数据处理

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整默认 PHP 构建并提供 CLI",
  "tests": "tests/lang 与 ext/json/tests",
  "deliverable": "可安装解释器"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B07",
  "project": "PHP",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/php/php-src",
    "acquisition_url": "https://codeload.github.com/php/php-src/tar.gz/c998c36b97d13cf936a9f5c4180d1104a6db6b80",
    "release_ref": "php-8.4.8",
    "commit": "c998c36b97d13cf936a9f5c4180d1104a6db6b80",
    "filename": "source.tar.gz",
    "bytes": 21063638,
    "sha256": "f53f9efb10bf5f843f3fc1de8043454fdea018058a651481825440c22ea6bb6f",
    "submodules_ready": true
  },
  "scope": {
    "scope": "完整默认 PHP 构建并提供 CLI",
    "tests": "tests/lang 与 ext/json/tests",
    "deliverable": "可安装解释器"
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
