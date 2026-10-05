# BUILDv1-A02 — 构建 Zstandard 工具与可嵌入压缩库

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"默认完整 CLI/库构建和 make check。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A02",
  "project": "Zstandard",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/facebook/zstd",
    "acquisition_url": "https://codeload.github.com/facebook/zstd/tar.gz/f8745da6ff1ad1e7bab384bd1f9d742439278e99",
    "release_ref": "v1.5.7",
    "commit": "f8745da6ff1ad1e7bab384bd1f9d742439278e99",
    "filename": "source.tar.gz",
    "bytes": 2453329,
    "sha256": "4b0bd1f0cfb25e61b9103c35f27395530ff5b4c0d2513a00fd745849e85ea52c",
    "submodules_ready": true
  },
  "scope": "默认完整 CLI/库构建和 make check。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
