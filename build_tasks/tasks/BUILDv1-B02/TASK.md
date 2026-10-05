# BUILDv1-B02 — 自举构建 GCC C/C++ 编译器与运行库

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "同一 C/C++ 目标，显式 --disable-bootstrap 的单次源码构建",
  "tests": "C execute 与官方 old-deja.exp=9805* C++ 子集",
  "deliverable": "完整 C/C++ 安装树；标明非 bootstrap"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B02",
  "project": "GCC",
  "profile": "core",
  "source": {
    "upstream_repo": "https://gcc.gnu.org/git/gcc.git",
    "acquisition_url": "https://ftp.gnu.org/gnu/gcc/gcc-14.2.0/gcc-14.2.0.tar.xz",
    "release_ref": "gcc-14.2.0",
    "commit": null,
    "filename": "source.tar.xz",
    "bytes": 92306460,
    "sha256": "a7b39bc69cbf9e25826c5a60ab26477001f7c08d85cec04bc0e29cabed6f3cc9",
    "submodules_ready": true
  },
  "scope": {
    "scope": "同一 C/C++ 目标，显式 --disable-bootstrap 的单次源码构建",
    "tests": "C execute 与官方 old-deja.exp=9805* C++ 子集",
    "deliverable": "完整 C/C++ 安装树；标明非 bootstrap"
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
