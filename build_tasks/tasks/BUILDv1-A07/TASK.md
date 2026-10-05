# BUILDv1-A07 — 构建带 TLS 支持的事件驱动库

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"完整核心/extra/pthreads 库与来源基础检查；显式不带 TLS。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-A07",
  "project": "libevent",
  "profile": "core",
  "source": {
    "upstream_repo": "https://github.com/libevent/libevent",
    "acquisition_url": "https://codeload.github.com/libevent/libevent/tar.gz/df3ecad3a040fd6d4fad4287defe113395de6fd7",
    "release_ref": "release-2.2.2-alpha",
    "commit": "df3ecad3a040fd6d4fad4287defe113395de6fd7",
    "filename": "source.tar.gz",
    "bytes": 873591,
    "sha256": "6d4f99414a48e40a572d4808e286367653390d5f7c728fe938517feb3d17797c",
    "submodules_ready": true
  },
  "scope": "完整核心/extra/pthreads 库与来源基础检查；显式不带 TLS。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "instance_revision": "core_libevent_2.2.2_alpha_real_dns_v3",
  "source_rebinding_reason": "Initial 2.1.12 full upstream regressions failed DNS-cancellation stress and monotonic precision on this container; bind a newer official release with unchanged core deliverable and complete upstream tests, without deleting failures or editing expected values.",
  "network_policy": "bridge",
  "network_exception_reason": "Official util/getaddrinfo resolves www.google.com and hostname_hints uses AI_ADDRCONFIG; provide real DNS and an addressed network interface instead of changing/filtering upstream tests. Target/dependency downloads remain forbidden."
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
