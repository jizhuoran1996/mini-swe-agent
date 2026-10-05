# BUILDv1-C06 — 构建无界面的 Blender 场景处理与 CPU 渲染发行包

This frozen instance uses the source-defined core profile. The original reference scope stays in source_spec.json and is not claimed complete by a core run.

## Required core scope

"官方 headless 完整应用、C/C++ 与几何/文件测试；只选择有限官方 render group。"

## Source and execution binding

```json
{
  "task_id": "BUILDv1-C06",
  "project": "Blender",
  "profile": "core",
  "source": {
    "upstream_repo": "https://projects.blender.org/blender/blender",
    "acquisition_url": "https://codeload.github.com/blender/blender/tar.gz/802179c51ccc68b776e7a2fad23503b961577013",
    "release_ref": "v4.4.3",
    "commit": "802179c51ccc68b776e7a2fad23503b961577013",
    "filename": "source.tar.gz",
    "bytes": 81108202,
    "sha256": "0608332f5c7974c0043c28be3317bbd17cdf271f0829f960fa84563411d736c6",
    "submodules_ready": false
  },
  "scope": "官方 headless 完整应用、C/C++ 与几何/文件测试；只选择有限官方 render group。",
  "build_jobs": 4,
  "test_jobs": 2,
  "source_archive_ready": true,
  "offline_dependencies_ready": false,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
