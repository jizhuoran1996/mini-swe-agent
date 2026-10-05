# BUILDv1-E03 — 构建 Flink 发行包并验收本地流处理

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"-pl flink-core -am 的完整构建与测试，交付核心 JAR 和独立序列化 consumer。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-E03",
  "project": "Apache Flink",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/apache/flink",
    "acquisition_url": "https://codeload.github.com/apache/flink/tar.gz/cb1e7b5571b06ebe3d79f57030663af3e83aefcd",
    "release_ref": "release-1.20.1",
    "commit": "cb1e7b5571b06ebe3d79f57030663af3e83aefcd",
    "filename": "source.tar.gz",
    "bytes": 40204944,
    "sha256": "82bf43c6fe515df0eab51081b32c97669edf22361ecf8a9861a7e41f242e5c1e",
    "submodules_ready": false
  },
  "scope": "-pl flink-core -am 的完整构建与测试，交付核心 JAR 和独立序列化 consumer。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "maven-wrapper-dependencies.tar.gz",
      "bytes": 17518698,
      "sha256": "9d93d1a3ac19ccef42ba57b6d7a13df17bd749f1e4de3879ea1fe5cf32031082",
      "preparation_run": "prepare_flink_wrapper_1791215041396437837",
      "target_outputs_exported": false
    },
    {
      "filename": "dependencies.tar.gz",
      "bytes": 203853562,
      "sha256": "f81495cae8031aa8e42f6395832aed8fae4c3f2375b899fc71ef999b583a1f89",
      "preparation_run": "prepare_BUILDv1-E03_1791217221035777351",
      "target_outputs_exported": false
    }
  ],
  "dependency_source_overlays": [
    {
      "filename": "maven-wrapper-3.2.0.jar",
      "sha256": "e63a53cfb9c4d291ebe3c2b0edacb7622bbc480326beaa5a0456e412f52f066a",
      "bytes": 62547,
      "source_relative_destination": ".mvn/wrapper/maven-wrapper.jar",
      "source": "https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.2.0/maven-wrapper-3.2.0.jar",
      "upstream_validation": "Exact SHA256 supplied by the frozen source; actual official wrapper bootstrap"
    }
  ],
  "maven_wrapper_bootstrap": {
    "target_compiled": false,
    "target_outputs_exported": false,
    "wrapper_version": "3.2.0",
    "distribution_version": "3.8.6",
    "distribution_sha256_from_frozen_source": "ccf20a80e75a17ffc34d47c5c95c98c39d426ca17d670f09cd91e877072a9309",
    "wrapper_jar_sha256": "e63a53cfb9c4d291ebe3c2b0edacb7622bbc480326beaa5a0456e412f52f066a",
    "cache_materialization": "genuine wrapper --version installation; native hydrator restores HOME/.m2/wrapper"
  },
  "maven_additional_artifacts": [
    "net.bytebuddy:byte-buddy-agent:1.14.4",
    "org.apache:apache-jar-resource-bundle:1.4",
    "org.javassist:javassist:3.24.0-GA",
    "org.apache.maven.surefire:surefire-junit-platform:3.2.2",
    "org.junit.platform:junit-platform-launcher:1.10.1"
  ],
  "maven_additional_artifact_basis": "Exact genuine external coordinates reported missing by the real offline reactor; dependency:get resolves originals and transitive inputs without target compilation",
  "dependency_resolution_status": {
    "kind": "maven",
    "target_compiled": false,
    "target_installation_exported": false,
    "cache_directories": [
      "maven"
    ],
    "dependency_resolution_completed": true,
    "cache_export_completed": true
  },
  "maven_settings": {
    "filename": "maven-central-settings.xml",
    "sha256": "276a36e3721bc10552c69249bf62d9916f6185d0e237c7b4ecbca0394ab51dcb",
    "bytes": 151,
    "mirror_id": "official-central",
    "mirror_url": "https://repo.maven.apache.org/maven2",
    "reason": "Use the same real repository identity for prepared cache and native offline build"
  }
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
