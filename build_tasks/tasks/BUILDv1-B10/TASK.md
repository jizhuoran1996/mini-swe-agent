# BUILDv1-B10 — 构建 OpenJDK 镜像并验收编译器与 JVM

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

{
  "scope": "完整 server JDK image",
  "tests": "jdk_lang",
  "deliverable": "可用 JDK 安装镜像"
}

## Source and execution binding

```json
{
  "task_id": "BUILDv1-B10",
  "project": "OpenJDK",
  "profile": "core",
  "source": {
    "upstream_repo": "https://git.openjdk.org/jdk",
    "acquisition_url": "https://codeload.github.com/openjdk/jdk21u/tar.gz/4215779271750e6409bdfbd6d94d16002bd9b6a7",
    "release_ref": "jdk-21.0.7+6",
    "commit": "4215779271750e6409bdfbd6d94d16002bd9b6a7",
    "filename": "source.tar.gz",
    "bytes": 113336081,
    "sha256": "1888a5b967240efc83d3786667af1b3b8f75de5646c96c39bfccc9e331d9e5e9",
    "submodules_ready": true
  },
  "scope": {
    "scope": "完整 server JDK image",
    "tests": "jdk_lang",
    "deliverable": "可用 JDK 安装镜像"
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
