# BUILDv1-B06 — 构建并安装 Ruby 解释器与标准扩展

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 Ruby 解释器和选定默认扩展",
  "tests": "make test 与 test/ruby/test_string.rb",
  "deliverable": "可运行安装树"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B06",
  "project": "Ruby",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/ruby/ruby",
    "acquisition_url": "https://codeload.github.com/ruby/ruby/tar.gz/a38531fd3f617bf734ef7d6c595325f69985ea1d",
    "release_ref": "v3_4_4",
    "commit": "a38531fd3f617bf734ef7d6c595325f69985ea1d",
    "filename": "source.tar.gz",
    "bytes": 16355757,
    "sha256": "5eba0e383a5546701d25bd2e182aeb87bbb0c78a88c38be73f7c876b6b5f8d73",
    "submodules_ready": true
  },
  "scope": {
    "scope": "完整 Ruby 解释器和选定默认扩展",
    "tests": "make test 与 test/ruby/test_string.rb",
    "deliverable": "可运行安装树"
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
