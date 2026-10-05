# BUILDv1-E02 — 构建 Spark SQL 发行包并交付本地分析程序

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"官方 -pl 子模块构建 core 及其 reactor 依赖并运行 DAGSchedulerSuite；交付 core JAR 和本地 RDD consumer。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-E02",
  "project": "Apache Spark",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/apache/spark",
    "acquisition_url": "https://codeload.github.com/apache/spark/tar.gz/ed00d046951a7ecda6429accd3b9c5b2dc792b65",
    "release_ref": "v3.5.7",
    "commit": "ed00d046951a7ecda6429accd3b9c5b2dc792b65",
    "filename": "source.tar.gz",
    "bytes": 34481233,
    "sha256": "c310db387f7db1f8e8282bea351b884e995f5b68eb47658927d2052cd76e3e9f",
    "submodules_ready": true
  },
  "scope": "官方 -pl 子模块构建 core 及其 reactor 依赖并运行 DAGSchedulerSuite；交付 core JAR 和本地 RDD consumer。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "dependencies.tar.gz",
      "bytes": 737413357,
      "sha256": "3762be61f6de91239d67a8a2f3ec9c8f70268f3b4df04a04be7eabb7f7246a8c",
      "preparation_run": "prepare_BUILDv1-E02_1791216761832204747",
      "target_outputs_exported": false
    }
  ],
  "dependency_resolution_status": {
    "kind": "maven",
    "target_compiled": false,
    "target_installation_exported": false,
    "cache_directories": [
      "maven"
    ],
    "dependency_resolution_completed": false,
    "cache_export_completed": true
  },
  "maven_settings": {
    "filename": "maven-central-settings.xml",
    "sha256": "276a36e3721bc10552c69249bf62d9916f6185d0e237c7b4ecbca0394ab51dcb",
    "bytes": 151,
    "mirror_id": "official-central",
    "mirror_url": "https://repo.maven.apache.org/maven2",
    "reason": "Use the same real repository identity for prepared cache and native offline build"
  },
  "maven_additional_artifacts": [
    "org.scala-lang:scala-reflect:2.12.18",
    "net.bytebuddy:byte-buddy-agent:1.14.4",
    "org.codehaus.mojo:extra-enforcer-rules:1.7.0"
  ],
  "maven_additional_artifact_basis": "Exact genuine external coordinates reported missing by the real offline reactor; dependency:get resolves originals and transitive inputs without target compilation"
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
