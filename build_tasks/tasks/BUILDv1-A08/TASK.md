# BUILDv1-A08 — 构建多编码正则与 JIT 开发包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整 8 位库及 grep，JIT 关闭，运行相应官方套件。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A08",
  "project": "PCRE2",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/PCRE2Project/pcre2",
    "acquisition_url": "https://codeload.github.com/PCRE2Project/pcre2/tar.gz/b2bd4254b379b9d7dc9a3dda060a7e27009ccdff",
    "release_ref": "pcre2-10.46",
    "commit": "b2bd4254b379b9d7dc9a3dda060a7e27009ccdff",
    "filename": "source.tar.gz",
    "bytes": 3270806,
    "sha256": "a5076fb46eaa1bae6d6596de73269ed0fb84204d40846cc5c7fdc27374912b70",
    "submodules_ready": false
  },
  "scope": "完整 8 位库及 grep，JIT 关闭，运行相应官方套件。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
