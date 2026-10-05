# BUILDv1-F04 — 构建 scikit-learn 原生扩展发行包并验证邻域搜索与模型流水线

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 wheel + KDTree 官方测试。"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-F04",
  "project": "scikit-learn",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/scikit-learn/scikit-learn",
    "acquisition_url": "https://files.pythonhosted.org/packages/9e/a5/4ae3b3a0755f7b35a280ac90b28817d1f380318973cff14075ab41ef50d9/scikit_learn-1.6.1.tar.gz",
    "release_ref": "1.6.1",
    "commit": null,
    "filename": "source.tar.gz",
    "bytes": 7068312,
    "sha256": "b4fc2525eca2c69a59260f583c56a7557c6ccdf8deafdba6e060f94c1c59738e",
    "submodules_ready": true
  },
  "scope": {
    "scope": "完整 wheel + KDTree 官方测试。"
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
