# BUILDv1-C06 — Headless Blender CPU source build

Source: `blender/blender` @ `802179c51ccc68b776e7a2fad23503b961577013` (v4.4.3),
archive `source.tar.gz` (sha256 `0608332f…d736c6`).

## Entry points

* `python3 solution/main.py --help` — usage, no build performed.
* `python3 solution/main.py doctor --input input` — prints a JSON report of the
exact missing source / tool / dependency items. Exit `0` when the tree is
ready to build, exit `78` when anything required is missing.
* `python3 solution/main.py run --input input --output output --jobs 4` — runs
`doctor` first, then configures with the official headless preset, compiles
with Ninja, installs, freezes and executes the frozen CORE CTest selection
(`bmesh_bevel`, `bmesh_boolean`, `mesh_join`, `mesh_validate`,
`blendfile_liblink`, `blendfile_relationships`, `cycles_mesh_cpu`) and finally
drives two independent consumer Blender processes that build a beveled scene,
save a `.blend`, reload it and render one CPU Cycles frame.

## Frozen CORE profile

* CMake preset `build_files/cmake/config/blender_headless.cmake`.
* `WITH_GTESTS=ON`, `WITH_CYCLES=ON`, `CYCLES_TEST_DEVICES=CPU`.
* All GPU backends (CUDA / OptiX / HIP / oneAPI binaries) and GPU render /
compositor tests are OFF, per the frozen contract.
* Build parallelism capped at 4, test parallelism capped at 2.

## Honest limitations

* `lib/linux_x64` is an update-disabled git submodule and is **not** contained
in the 81 MB source tarball. It holds the prebuilt third-party dependencies
(OpenEXR, OpenImageIO, OpenColorIO, OpenSubdiv, OpenVDB, PNG/JPEG, Boost,
Python, FFmpeg, …). Without it CMake cannot configure and no target product
can be produced. `doctor` detects this and `run` refuses with exit `78`
rather than faking a build.
* The supplied environment has no network access, so the bundle cannot be
acquired at build time; it must be materialized by the instance builder and
the command retried.
* `tests/data` (Blender test-data submodule) and the pinned `oiiotool` are
likewise required for the render/geometry regression data; if they are absent
the corresponding CTest cases are not registered and `run` reports the
missing selectors instead of silently skipping them.
* A headless CPU build does not exercise GUI, Eevee, physical GPU or window
system paths.
