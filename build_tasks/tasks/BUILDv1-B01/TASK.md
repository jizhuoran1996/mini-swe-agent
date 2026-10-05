# BUILDv1-B01 — 构建并交付 LLVM/Clang 本机 C/C++ 工具链

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "X86 + clang；不启用 lld",
  "tests": "check-llvm-unit 与 check-clang",
  "deliverable": "可运行的本机 Clang 安装树"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B01",
  "project": "LLVM / Clang",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/llvm/llvm-project",
    "acquisition_url": "https://codeload.github.com/llvm/llvm-project/tar.gz/87f0227cb60147a26a1eeb4fb06e3b505e9c7261",
    "release_ref": "llvmorg-20.1.8",
    "commit": "87f0227cb60147a26a1eeb4fb06e3b505e9c7261",
    "filename": "source.tar.gz",
    "bytes": 226918818,
    "sha256": "ccd2521c73309446f3811ec78e5702e92c5fdf259ec4a82b067f7121da29db05",
    "submodules_ready": true
  },
  "scope": {
    "scope": "X86 + clang；不启用 lld",
    "tests": "check-llvm-unit 与 check-clang",
    "deliverable": "可运行的本机 Clang 安装树"
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
