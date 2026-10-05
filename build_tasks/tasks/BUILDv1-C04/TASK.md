# BUILDv1-C04 — 构建流式图像处理 C/C++ SDK

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"CPU 核心库、C++ API、PNG/JPEG/TIFF 和列出的官方 Meson 测试。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C04",
  "project": "libvips",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/libvips/libvips",
    "acquisition_url": "https://codeload.github.com/libvips/libvips/tar.gz/82c7c05cb02a52750251bb4cc69d67f40568cf98",
    "release_ref": "v8.16.1",
    "commit": "82c7c05cb02a52750251bb4cc69d67f40568cf98",
    "filename": "source.tar.gz",
    "bytes": 33515998,
    "sha256": "ba68f72913361cbf1da83fd45a60b4ade74967c1398ca1dfc8927e8ae4ca5b95",
    "submodules_ready": true
  },
  "scope": "CPU 核心库、C++ API、PNG/JPEG/TIFF 和列出的官方 Meson 测试。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
