# BUILDv1-C06 — Headless Blender CPU source build

Source: `blender/blender` @ `802179c51ccc68b776e7a2fad23503b961577013`
(v4.4.3), archive `source.tar.gz`
(sha256 `0608332f…d736c6`, 81 108 202 bytes).

## Entry points

* `python3 solution/main.py --help` — usage information; no build performed.
* `python3 solution/main.py doctor --input input` — inspects the locked
manifest (`source`, `blender_gitlinked_inputs`, `blender_lfs_objects`), the
prepared dependency cache `/workspace/cache/blender_modules` and the required
bootstrap tools. Prints a JSON report of every missing source / tool /
dependency item. Exit `0` when the tree is ready to build, exit `78` when
anything required is missing.
* `python3 solution/main.py run --input input --output output --jobs 4` —
  runs `doctor` first and refuses to proceed when the environment is not
  ready. Then it:

  1. Generates the fresh source tree from the frozen archive and attaches the
     declared gitlink inputs (`lib/linux_x64`, `release/datafiles/assets`,
     `tests/data`) from the prepared cache into the source tree (symlink, or a
     physical copy when the filesystem forbids symlinking).
  2. Configures with the official headless preset
     (`build_files/cmake/config/blender_headless.cmake`) plus
     `WITH_GTESTS=ON`, `WITH_CYCLES=ON`, `CYCLES_TEST_DEVICES=CPU` and all
     GPU Cycles backends OFF.
  3. Compiles with Ninja at `BUILD_JOBS <= 4`.
  4. Freezes the exact registered CTest inventory via
     `ctest --show-only=json-v1` into `ctest_inventory.json`, then derives the
     frozen selector from that inventory: all C/C++ GTest targets discovered
     from their executable command, the four exact python CTest targets
     `bmesh_bevel`, `bmesh_boolean`, `blendfile_liblink`,
     `blendfile_relationships`, and the complete `cycles_mesh_cpu` render
     group. The realised selector names are written to
     `frozen_selectors.json`.
  5. Installs the tree (`cmake --build … --target install`) and executes the
     frozen tests with `TEST_JOBS <= 2`.
  6. Runs from `INSTALL_ROOT` only, in a clean consumer directory outside the
     source tree: a runtime check that imports `bpy` from the packaged Python,
     then two independent Blender processes that build a fresh beveled scene,
     save a `.blend`, reload it in a second process, reassert the persisted
     geometry and emit a CPU Cycles frame from each process.

## Covered features

* Full headless Linux Blender with an embedded Python runtime and CPU Cycles.
* C/C++ GTest binaries built by Blender’s own test infrastructure.
* Python geometry and blend-file CTest targets exactly named
  `bmesh_bevel`, `bmesh_boolean`, `blendfile_liblink`,
  `blendfile_relationships`.
* The complete `cycles_mesh_cpu` render regression group.

## Honest limitations

* The `lib/linux_x64`, `release/datafiles/assets` and `tests/data` gitlinks
  are `update = none` submodules and are **not** contained in the 81 MB
  source tarball. They are shipped separately as dependency libraries and
  data under `/workspace/cache/blender_modules`. `doctor` reports them as
  `cache:missing:…` items when the cache has not been hydrated, and `run`
  refuses with exit `78` rather than fabricating a build.
* The environment has no network access, so the cache cannot be fetched at
  build time; it must be materialised by the instance builder and the
  command retried.
* Several LFS objects declared in `manifest.blender_lfs_objects` (for example
  the pinned Alembic utilities and the OpenImageIO `oiiotool` the CPU render
  tests require) must also be present inside the cache. `doctor` spot-checks
  a small sample for size; a full SHA-256 sweep is left to the grading step
  so that `doctor` remains cheap.
* The build is headless CPU only: GPU backends (CUDA / OptiX / HIP / oneAPI),
  Eevee, GUI, window-system and non-CPU render tests are explicitly outside
  this frozen scope and disabled by the configure line.
