# BUILDv1-F05 — 编译 NumPy 数组运行时及开发接口发行包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 wheel + linalg 基础测试。"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-F05",
  "project": "NumPy",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/numpy/numpy",
    "acquisition_url": "https://files.pythonhosted.org/packages/76/21/7d2a95e4bba9dc13d043ee156a356c0a8f0c6309dff6b21b4d71a073b8a8/numpy-2.2.6.tar.gz",
    "release_ref": "2.2.6",
    "commit": null,
    "filename": "source.tar.gz",
    "bytes": 20276440,
    "sha256": "e29554e2bef54a90aa5cc07da6ce955accb83f21ab5de01a62c8478897b264fd",
    "submodules_ready": false
  },
  "scope": {
    "scope": "完整 wheel + linalg 基础测试。"
  },
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "target_bootstrap_policy": {
    "matching_target_package_installed": false,
    "prebuilt_target_wheel_visible": false,
    "image": "sbench-build-runtime:numpy-clean",
    "notes": "Clean target-specific overlay removes bootstrap target distributions and their wheelhouse files; other libraries remain genuine build/test dependencies."
  }
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
