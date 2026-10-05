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
  "offline_dependencies_ready": true,
  "target_build_outputs_preloaded": false,
  "optional_incremental_enabled": false,
  "dependency_caches": [
    {
      "filename": "blender-dependencies.tar.gz",
      "sha256": "bfdecbbf62febd3a2f80979ff5a4a4a0496728e4527bffcebb3332224274f5ff",
      "bytes": 1240011239,
      "target_outputs_exported": false,
      "destination": "/workspace/cache/blender_modules",
      "contents": "Official third-party libraries and test assets; no Blender target binary"
    }
  ],
  "blender_gitlinked_inputs": [
    {
      "path": "lib/linux_x64",
      "repository": "lib-linux_x64",
      "commit": "3cf676e54a5be98285c6d47633fbe1f26929bb5a",
      "archive_url": "https://projects.blender.org/api/v1/repos/blender/lib-linux_x64/archive/3cf676e54a5be98285c6d47633fbe1f26929bb5a.tar.gz",
      "archive_sha256": "3d6cbb9c1d7ee1181197732a03f0987fbcba9745d4cb6b9ad69a2862b50afd17",
      "excluded_paths": []
    },
    {
      "path": "release/datafiles/assets",
      "repository": "blender-assets",
      "commit": "0418ad6b8e0d962bde30b2d4d828984b9f9c3299",
      "archive_url": "https://projects.blender.org/api/v1/repos/blender/blender-assets/archive/0418ad6b8e0d962bde30b2d4d828984b9f9c3299.tar.gz",
      "archive_sha256": "38fe9b051a9f9475a2f1aea1e1cb105a03c4b36ebd13bdf6630a33a6ac823360",
      "excluded_paths": [
        "working/"
      ]
    },
    {
      "path": "tests/data",
      "repository": "blender-test-data",
      "commit": "01b8fd393e61e72d6d86d1740c42e82820c3e7a5",
      "archive_url": "https://projects.blender.org/api/v1/repos/blender/blender-test-data/archive/01b8fd393e61e72d6d86d1740c42e82820c3e7a5.tar.gz",
      "archive_sha256": "eb39108dc52d6eb07e266b8e68cf310320100e92789173a5c26032f493699cb7",
      "excluded_paths": []
    }
  ],
  "blender_lfs_objects": {
    "count": 6196,
    "full_records": "input/manifest.json#blender_lfs_objects"
  }
}
```

Build the declared complete target from source; run nonempty official tests with exact selectors/inventory and preserved expected results; install/package it and consume those new artifacts outside the source tree. Save commands.json, tests.json, upstream logs, install_manifest.json, install.tar.gz (or source-built wheel), and run.json. Compilation, upstream tests, independent acceptance and formal reference execution are separate states. The controller supplies the buildkit Session helper.
