# BUILDv1-B04 — 构建含数据库与并发支持的 CPython 发行目录

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 CPython 与数据库/编码扩展",
  "tests": "test_json/test_sqlite3/test_importlib",
  "deliverable": "可安装解释器和标准库"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B04",
  "project": "CPython",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/python/cpython",
    "acquisition_url": "https://codeload.github.com/python/cpython/tar.gz/0cc81280367df838c4b199f8f0378837165071c2",
    "release_ref": "v3.12.10",
    "commit": "0cc81280367df838c4b199f8f0378837165071c2",
    "filename": "source.tar.gz",
    "bytes": 27629197,
    "sha256": "6e54563e8c3433e7ca89dd85784c1f6f478bb55c11220c7c11336a9b659a35c8",
    "submodules_ready": true
  },
  "scope": {
    "scope": "完整 CPython 与数据库/编码扩展",
    "tests": "test_json/test_sqlite3/test_importlib",
    "deliverable": "可安装解释器和标准库"
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
