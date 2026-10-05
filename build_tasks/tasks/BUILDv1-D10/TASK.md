# BUILDv1-D10 — 构建并验证 Envoy 代理发行二进制

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"构建 envoy-static 与 header_map_impl_test，进行单路由本地消费者。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-D10",
  "project": "Envoy",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/envoyproxy/envoy",
    "acquisition_url": "https://codeload.github.com/envoyproxy/envoy/tar.gz/c657e59fac461e406c8fdbe57ced833ddc236ee1",
    "release_ref": "v1.34.2",
    "commit": "c657e59fac461e406c8fdbe57ced833ddc236ee1",
    "filename": "source.tar.gz",
    "bytes": 24494200,
    "sha256": "611eec605b33765639f4eb3ebd4b4bd63ca10de9372b73eb78df167c4cefa692",
    "submodules_ready": true
  },
  "scope": "构建 envoy-static 与 header_map_impl_test，进行单路由本地消费者。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "bazel-dependencies.tar.gz",
      "bytes": 2360411656,
      "sha256": "9822f7729dad4e9efc08e7612ef26f3334ce9a399a9cf878cba5bfc28cbe6c0c",
      "preparation_run": "prepare_bazel_BUILDv1-D10_1791194551214121658",
      "target_outputs_exported": false
    }
  ],
  "bazel_dependency_preparation": {
    "bazel_version": "7.6.0",
    "targets": [
      "//source/exe:envoy-static",
      "//test/common/http:header_map_impl_test"
    ],
    "target_compiled": false,
    "target_installation_exported": false,
    "cache_directories": [
      "bazel_repository",
      "bazel_output/external"
    ]
  }
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
