# BUILDv1-A01 — 构建并交付 zlib 压缩开发包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整静态库与 teststatic，适于最小工程调通。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A01",
  "project": "zlib",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/madler/zlib",
    "acquisition_url": "https://codeload.github.com/madler/zlib/tar.gz/51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf",
    "release_ref": "v1.3.1",
    "commit": "51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf",
    "filename": "source.tar.gz",
    "bytes": 1572004,
    "sha256": "d9e270d46252734aa49770fbc544125391617956266f220bd63216c834f3a522",
    "submodules_ready": true
  },
  "scope": "完整静态库与 teststatic，适于最小工程调通。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
