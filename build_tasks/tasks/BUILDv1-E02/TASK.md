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
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "dependencies.tar.gz",
      "bytes": 766781160,
      "sha256": "0b1847be3b93e06ccf21520987c6def9056e167de9619cc5da8f291a757bd603",
      "preparation_run": "prepare_BUILDv1-E02_1791220179936323998",
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
    "org.codehaus.mojo:extra-enforcer-rules:1.7.0",
    "org.apache:apache-jar-resource-bundle:1.4",
    "org.scala-sbt:compiler-bridge_2.12:1.8.0:jar:sources",
    "org.scala-lang:scala-compiler:2.12.17",
    "org.scala-lang:scala-compiler:2.12.18",
    "com.github.ghik:silencer-plugin_2.12.18:1.7.13",
    "com.nimbusds:nimbus-jose-jwt:3.10",
    "com.google.protobuf:protoc:3.23.4:exe:linux-x86_64"
  ],
  "maven_additional_artifact_basis": "Exact genuine external coordinates reported missing by the real offline reactor; dependency:get resolves originals and transitive inputs without target compilation",
  "maven_bootstrap": {
    "url": "https://archive.apache.org/dist/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz",
    "filename": "apache-maven-3.9.6-bin.tar.gz",
    "sha256": "6eedd2cae3626d6ad3a5c9ee324bd265853d64297f07f033430755bd0e0c3a4b",
    "sha512": "706f01b20dec0305a822ab614d51f32b07ee11d0218175e55450242e49d2156386483b506b3a4e8a03ac8611bae96395fd5eec15f50d3013d5deed6d1ee18224",
    "official_checksum_url": "https://archive.apache.org/dist/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz.sha512",
    "role": "genuine source build bootstrap only; no Spark binaries",
    "version": "3.9.6"
  },
  "offline_dependency_runtime_verification": {
    "run_directory": "/home/zrji/sbench/build_suite/tasks/BUILDv1-E02/runs/20261006_013417_trial_1791221657830277312",
    "full_source_build_passed": true,
    "selected_official_suite": "DAGSchedulerSuite",
    "official_cases_passed": 127,
    "fresh_container_consumer_passed": true,
    "dependency_caches": [
      {
        "filename": "dependencies.tar.gz",
        "bytes": 766781160,
        "sha256": "0b1847be3b93e06ccf21520987c6def9056e167de9619cc5da8f291a757bd603",
        "preparation_run": "prepare_BUILDv1-E02_1791220179936323998",
        "target_outputs_exported": false
      }
    ],
    "basis": "Actual full cold source build, all 127 unchanged upstream cases, installed-only SDK consumer and independent new-container RDD consumer using these exact locked input archives. Separate go-offline plugin/report resolution status remains unchanged."
  }
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
