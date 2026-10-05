# BUILDv1-A10 — 构建可嵌入 Git 工作区管理开发包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整库和固定本地 repo/object/index 子集，子集须从绑定版本 Clar inventory 解析。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A10",
  "project": "libgit2",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/libgit2/libgit2",
    "acquisition_url": "https://codeload.github.com/libgit2/libgit2/tar.gz/0060d9cf5666f015b1067129bd874c6cc4c9c7ac",
    "release_ref": "v1.9.1",
    "commit": "0060d9cf5666f015b1067129bd874c6cc4c9c7ac",
    "filename": "source.tar.gz",
    "bytes": 7652737,
    "sha256": "7efaf8f564c7a2c0f5cf475f80c91fc003e529e66643b07b9265320f55b0664b",
    "submodules_ready": true
  },
  "scope": "完整库和固定本地 repo/object/index 子集，子集须从绑定版本 Clar inventory 解析。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
