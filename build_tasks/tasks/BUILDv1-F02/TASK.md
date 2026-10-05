# BUILDv1-F02 — 从源码交付 TensorFlow CPU wheel 与可重载模型支持

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 CPU wheel，加两个文档示范组件的有限测试。"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-F02",
  "project": "TensorFlow",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/tensorflow/tensorflow",
    "acquisition_url": "https://codeload.github.com/tensorflow/tensorflow/tar.gz/6550e4bd80223cdb8be6c3afd1f81e86a4d433c3",
    "release_ref": "v2.18.0",
    "commit": "6550e4bd80223cdb8be6c3afd1f81e86a4d433c3",
    "filename": "source.tar.gz",
    "bytes": 80324425,
    "sha256": "403916fbcfcbd5657cd891a871debc72433d7a8c56760297a79085e1abc8f18a",
    "submodules_ready": true
  },
  "scope": {
    "scope": "完整 CPU wheel，加两个文档示范组件的有限测试。"
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
