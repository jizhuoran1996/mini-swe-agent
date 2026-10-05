# BUILDv1-F03 — 编译 JAX 的 CPU jaxlib/XLA 并交付配套 wheel

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "CPU jaxlib+JAX；执行官方 pad 子集。"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-F03",
  "project": "JAX/jaxlib",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/jax-ml/jax",
    "acquisition_url": "https://codeload.github.com/jax-ml/jax/tar.gz/c8032a9904eeb2410995425f817929f507fe22d5",
    "release_ref": "jax-v0.5.3",
    "commit": "c8032a9904eeb2410995425f817929f507fe22d5",
    "filename": "source.tar.gz",
    "bytes": 15930790,
    "sha256": "44f52fe4dd529c40ddce4d22bee62ec99cba8bb9119b3e668176d44c2e4fad17",
    "submodules_ready": true
  },
  "scope": {
    "scope": "CPU jaxlib+JAX；执行官方 pad 子集。"
  },
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "bazel-dependencies.tar.gz",
      "bytes": 1411815235,
      "sha256": "c104a5220521d831d4286063c4fdf780c82f51e99036725257977f54c460b48a",
      "preparation_run": "prepare_bazel_BUILDv1-F03_1791199427494595911",
      "target_outputs_exported": false
    }
  ],
  "bazel_dependency_preparation": {
    "bazel_version": "7.4.1",
    "targets": [
      "//jaxlib/tools:build_wheel"
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
