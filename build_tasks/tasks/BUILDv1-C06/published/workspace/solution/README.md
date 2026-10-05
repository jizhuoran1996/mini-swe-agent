# BUILDv1-C06 - Headless Blender CPU source build

Source: blender/blender @ 802179c51ccc68b776e7a2fad23503b961577013 (v4.4.3),
archive source.tar.gz (sha256 0608332f...d736c6, 81108202 bytes).

## Entry points

* python3 solution/main.py --help - usage, no build.
* python3 solution/main.py doctor --input input - inspect the locked manifest,
source archive, prepared dependency cache /workspace/cache/blender_modules and
required tools. Verifies:
  - archive SHA-256 against the frozen value
  - cmake/ninja/gcc/g++/python3 on PATH
  - the three declared gitlink inputs (lib/linux_x64, release/datafiles/assets,
tests/data) present and non-empty in cache
  - real lib/linux_x64 bundle content: the anchor file epoxy/lib/libepoxy.a
hashes to 453c3b98...154d0f97 (frozen lib-linux_x64 LFS digest) and epoxy/,
python/ trees are materialised
  - all 6196 blender_lfs_objects records resolve to hydrated cache files, are
not still LFS pointer stubs, match declared byte size, and (when the manifest
record carries a 64-hex oid/sha256) match SHA-256 exactly
Exit 0 when ready to build, 78 when anything required is missing.

* python3 solution/main.py run --input input --output output --jobs 4 -
runs doctor first, refuses on 78, then:
  1. Extracts the frozen source archive and attaches the declared gitlink
     inputs from cache into the source tree (symlink or copy).
  2. Configures with the official headless preset
     (build_files/cmake/config/blender_headless.cmake) plus explicit
     -DLIBDIR=<src>/lib/linux_x64 -DWITH_LIBS_PRECOMPILED=ON (the archive
     inputs carry no .git metadata for platform_unix.cmake auto-selection),
     WITH_GTESTS=ON, WITH_CYCLES=ON, CYCLES_TEST_DEVICES=CPU and every GPU
     Cycles backend OFF. No git metadata is forged.
  3. Builds with Ninja at BUILD_JOBS <= 4.
  4. Freezes the exact registered CTest inventory via
     ctest --show-only=json-v1 into ctest_inventory.json, then derives the
     selector from that inventory: every C/C++ GTest target discovered from
     its executable path, the four exact python targets bmesh_bevel,
     bmesh_boolean, blendfile_liblink, blendfile_relationships, and the
     complete cycles_mesh_cpu render group. Writes frozen_selectors.json.
  5. Installs (cmake --build <build> --target install) and runs the frozen
     tests with TEST_JOBS <= 2.
  6. Runs from INSTALL_ROOT only: a bpy runtime check, then two independent
     Blender processes that build a fresh beveled scene, save a .blend,
     reload it in a second process, reassert geometry persistence and emit
     a CPU Cycles frame each.

## Honest limitations

* lib/linux_x64, release/datafiles/assets and tests/data are update=none
  submodules and are not inside the 81 MB tarball; they ship separately
  under /workspace/cache/blender_modules. doctor reports cache:missing:* and
  run refuses with 78 rather than fabricating a build.
* No network access: the cache must be materialised by the instance builder
  before this driver runs.
* doctor performs a full existence check on all 6196 declared LFS records
  and hashes those whose manifest entry carries a SHA-256 (including the
  frozen epoxy anchor). It does not attempt to reconstruct .git for
  submodules.
* Headless CPU only: GPU backends (CUDA/OptiX/HIP/oneAPI), Eevee, GUI,
  window-system and non-CPU render tests are outside this frozen scope and
  disabled in the configure line.
