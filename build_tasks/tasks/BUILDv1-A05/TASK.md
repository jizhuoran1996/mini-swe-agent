# BUILDv1-A05 — 构建密码与 TLS 软件开发包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整 build_sw + RSA/DSA 来源测试，用于构建链路调通。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A05",
  "project": "OpenSSL",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/openssl/openssl",
    "acquisition_url": "https://codeload.github.com/openssl/openssl/tar.gz/0893a62353583343eb712adef6debdfbe597c227",
    "release_ref": "openssl-3.5.2",
    "commit": "0893a62353583343eb712adef6debdfbe597c227",
    "filename": "source.tar.gz",
    "bytes": 53368267,
    "sha256": "85497d13fb31b8795efac2fdcfe3fdbf05038f726807dbc6253a61de5a668d75",
    "submodules_ready": true
  },
  "scope": "完整 build_sw + RSA/DSA 来源测试，用于构建链路调通。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
