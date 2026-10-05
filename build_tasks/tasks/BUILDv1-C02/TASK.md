# BUILDv1-C02 — 构建插件化媒体 SDK 与离线音视频管线

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"core + 基础 app/audio/video conversion 插件和对应 unit tests。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C02",
  "project": "GStreamer",
  "profile": "core",
  "source": {
    "upstream_repo": "https://gitlab.freedesktop.org/gstreamer/gstreamer",
    "acquisition_url": "https://codeload.github.com/GStreamer/gstreamer/tar.gz/100c21e1faf68efe7f3830b6e9f856760697ab48",
    "release_ref": "1.26.2",
    "commit": "100c21e1faf68efe7f3830b6e9f856760697ab48",
    "filename": "source.tar.gz",
    "bytes": 37237835,
    "sha256": "d769b7158fe3865fe2b232d1f6bc726ea58f6f3db91bfa2cf5d1f6d3f70bacc9",
    "submodules_ready": false
  },
  "scope": "core + 基础 app/audio/video conversion 插件和对应 unit tests。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
