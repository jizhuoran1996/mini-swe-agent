# BUILDv1-B03 — 构建并验收 ELF 汇编、链接与归档工具

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "本机 binutils/gas/ld",
  "tests": "check-binutils/check-gas 与 ld-shared/shared.exp",
  "deliverable": "完整基础 ELF 工具包"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B03",
  "project": "GNU binutils",
  "profile": "core",
  "source": {
    "upstream_repo": "https://sourceware.org/git/binutils-gdb.git",
    "acquisition_url": "https://ftp.gnu.org/gnu/binutils/binutils-2.44.tar.xz",
    "release_ref": "binutils-2.44",
    "commit": null,
    "filename": "source.tar.xz",
    "bytes": 27285788,
    "sha256": "ce2017e059d63e67ddb9240e9d4ec49c2893605035cd60e92ad53177f4377237",
    "submodules_ready": true
  },
  "scope": {
    "scope": "本机 binutils/gas/ld",
    "tests": "check-binutils/check-gas 与 ld-shared/shared.exp",
    "deliverable": "完整基础 ELF 工具包"
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
