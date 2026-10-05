# BUILDv1-F06 — 构建 SciPy 多语言数值 wheel 并验证线性代数与优化

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 CPU wheel + linalg 非 slow tests。"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-F06",
  "project": "SciPy",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/scipy/scipy",
    "acquisition_url": "https://files.pythonhosted.org/packages/0f/37/6964b830433e654ec7485e45a00fc9a27cf868d622838f6b6d9c5ec0d532/scipy-1.15.3.tar.gz",
    "release_ref": "1.15.3",
    "commit": null,
    "filename": "source.tar.gz",
    "bytes": 59419214,
    "sha256": "eae3cf522bc7df64b42cad3925c876e1b0b6c35c1337c93e12c0f366f55b0eaf",
    "submodules_ready": true
  },
  "scope": {
    "scope": "完整 CPU wheel + linalg 非 slow tests。"
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
