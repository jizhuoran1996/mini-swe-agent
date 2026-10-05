# BUILDv1-D09 — 构建并交付支持 TLS 的 NGINX 代理包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"标准 HTTP 构建 + proxy.t/ssi.t 与静态/代理消费者。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D09",
  "project": "NGINX",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/nginx/nginx",
    "acquisition_url": "https://codeload.github.com/nginx/nginx/tar.gz/481d28cb4e04c8096b9b6134856891dc52ecc68f",
    "release_ref": "release-1.28.0",
    "commit": "481d28cb4e04c8096b9b6134856891dc52ecc68f",
    "filename": "source.tar.gz",
    "bytes": 1263228,
    "sha256": "0eada60cd74e19eda887d822c8f6f2e22b18e4babbe0b2856b9210bb7067e1b4",
    "submodules_ready": true
  },
  "scope": "标准 HTTP 构建 + proxy.t/ssi.t 与静态/代理消费者。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "official_test_sources": [
    {
      "repo": "https://github.com/nginx/nginx-tests",
      "commit": "0b708546a8ae4e3cc737fdaeff349f1fd4b411b6",
      "acquisition_url": "https://codeload.github.com/nginx/nginx-tests/tar.gz/0b708546a8ae4e3cc737fdaeff349f1fd4b411b6",
      "filename": "nginx-tests.tar.gz",
      "sha256": "4e1c00dda31b23527262f2ab07f29361ada179617a618c6f73669ccf15d2f1ec",
      "bytes": 369057
    }
  ]
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
