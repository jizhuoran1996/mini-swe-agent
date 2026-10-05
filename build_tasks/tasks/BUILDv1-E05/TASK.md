# BUILDv1-E05 — 构建本机 Elasticsearch 分发并验收查询

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"只构建 server JAR 与查询包单元测试；交付独立 Java API 验证，明确不是完整服务。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-E05",
  "project": "Elasticsearch",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/elastic/elasticsearch",
    "acquisition_url": "https://codeload.github.com/elastic/elasticsearch/tar.gz/dbcbbbd0bc4924cfeb28929dc05d82d662c527b7",
    "release_ref": "v8.17.6",
    "commit": "dbcbbbd0bc4924cfeb28929dc05d82d662c527b7",
    "filename": "source.tar.gz",
    "bytes": 143598815,
    "sha256": "c064a59611f5ed38f06dce6bd1669fd05dc375e8b1923a88a2c66bf9dddef327",
    "submodules_ready": true
  },
  "scope": "只构建 server JAR 与查询包单元测试；交付独立 Java API 验证，明确不是完整服务。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "dependencies.tar.gz",
      "bytes": 1330864210,
      "sha256": "9ce702b238a9acda85d3607839b05f7f083face9d1a4f158b3347cd30c8802cd",
      "preparation_run": "prepare_BUILDv1-E05_1791219337710117655",
      "target_outputs_exported": false
    }
  ],
  "gradle_additional_artifacts": [
    "net.java.dev.jna:jna:5.12.1",
    "com.fasterxml.jackson.core:jackson-core:2.17.2",
    "com.fasterxml.jackson.dataformat:jackson-dataformat-smile:2.17.2",
    "com.fasterxml.jackson.dataformat:jackson-dataformat-yaml:2.17.2",
    "com.fasterxml.jackson.dataformat:jackson-dataformat-cbor:2.17.2"
  ],
  "gradle_additional_artifact_basis": "Exact genuine external coordinates demanded by the real upstream server test graph; ordinary Gradle resolution into the frozen dependency cache",
  "dependency_resolution_status": {
    "kind": "gradle",
    "target_compiled": false,
    "target_installation_exported": false,
    "cache_directories": [
      "gradle"
    ],
    "dependency_resolution_completed": true,
    "cache_export_completed": true
  },
  "gradle_additional_configurations": [
    {
      "project": ":libs:native:native-libraries",
      "configuration": "libs"
    }
  ],
  "java22_bootstrap": {
    "url": "https://github.com/adoptium/temurin22-binaries/releases/download/jdk-22.0.2%2B9/OpenJDK22U-jdk_x64_linux_hotspot_22.0.2_9.tar.gz",
    "filename": "OpenJDK22U-jdk_x64_linux_hotspot_22.0.2_9.tar.gz",
    "sha256": "05cd9359dacb1a1730f7c54f57e0fed47942a5292eb56a3a0ee6b13b87457a43",
    "official_metadata_url": "https://api.adoptium.net/v3/assets/latest/22/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse",
    "official_metadata_sha256": "a96a409f2b54849d284b1b48f79ab09705bef288171fd2306850c404abb3a6ef",
    "version": "22.0.2+9",
    "role": "genuine Java22 bootstrap for required multi-release source compilation; no Elasticsearch target binary"
  }
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
