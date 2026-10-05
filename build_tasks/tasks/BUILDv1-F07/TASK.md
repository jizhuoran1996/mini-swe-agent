# BUILDv1-F07 — 构建 pandas Cython 发行包并验收分组与时间索引

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 pandas wheel + libs/tslibs tests。"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-F07",
  "project": "pandas",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/pandas-dev/pandas",
    "acquisition_url": "https://files.pythonhosted.org/packages/9c/d6/9f8431bacc2e19dca897724cd097b1bb224a6ad5433784a44b587c7c13af/pandas-2.2.3.tar.gz",
    "release_ref": "2.2.3",
    "commit": null,
    "filename": "source.tar.gz",
    "bytes": 4399213,
    "sha256": "4f18ba62b61d7e192368b84517265a99b4d7ee8912f8708660fb4a366cc82667",
    "submodules_ready": true
  },
  "scope": {
    "scope": "完整 pandas wheel + libs/tslibs tests。"
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
