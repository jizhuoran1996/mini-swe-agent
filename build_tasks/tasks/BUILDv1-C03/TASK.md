# BUILDv1-C03 — 交付可开发和可测试的图像处理安装包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"PNG/JPEG/TIFF 图像 CLI 与开发库，冻结适用的官方测试选择。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C03",
  "project": "ImageMagick",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/ImageMagick/ImageMagick",
    "acquisition_url": "https://codeload.github.com/ImageMagick/ImageMagick/tar.gz/82572afc879b439cbf8c9c6f3a9ac7626adf98fb",
    "release_ref": "7.1.1-47",
    "commit": "82572afc879b439cbf8c9c6f3a9ac7626adf98fb",
    "filename": "source.tar.gz",
    "bytes": 15686050,
    "sha256": "b65c597e803ad526d0f8654e69c83d017508fd3de07b4a22ddcfaae9b989d822",
    "submodules_ready": true
  },
  "scope": "PNG/JPEG/TIFF 图像 CLI 与开发库，冻结适用的官方测试选择。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
