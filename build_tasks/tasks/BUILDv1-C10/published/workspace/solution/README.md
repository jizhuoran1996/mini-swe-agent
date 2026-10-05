# BUILDv1-C10 (core profile) - VTK Common/Filters/IO SDK

## What this builds

From the frozen VTK source release (commit `13acb1a5dd0ad7f7635f2511f44e599733643d06`,
v9.4.2) this builder performs a clean, out-of-source, offline CMake/Ninja build of a
**non-rendering** scientific SDK and installs it under the output tree.

Enabled modules (forced `YES`, dependencies pulled in transitively):

* `CommonCore`, `CommonDataModel`, `CommonExecutionModel`
* `FiltersCore`, `FiltersGeneral`, `FiltersSources`
* `IOLegacy`, `IOXML`
* `octree` - required leaf dependency: with `VTK_BUILD_TESTING=WANT` the module
  scan (`CMake/vtkModule.cmake:2856`) reaches `VTK::RenderingLabel` through the
  test closure, and that module hard-requires `VTK::octree`. Enabling that leaf
  module explicitly is the documented fix; it does **not** enable any rendering
  capability - the Rendering group stays `DONT_WANT`.

The Rendering group is set to `DONT_WANT`; MPI, Qt, Web, Tk and Python/Java wrapping
are disabled. This matches the frozen CORE profile ("Common/Filters/IO 多模块 SDK 与
非渲染 C++ test suites"). The Mesa/EGL offscreen rendering path belongs to the
separate **reference** profile and is intentionally not built here.

## Commands

```
# read-only prerequisite check (no build); exits 78 when something is missing
python3 solution/main.py doctor --input /workspace/input

# full clean build + install + official tests + independent consumer
python3 solution/main.py run --input /workspace/input \
                             --output /workspace/output --jobs 4
```

`--help` prints usage without touching the source tree.

## What is verified

1. Source archive checksum is re-computed against the manifest before extraction.
2. Official CTest inventory is captured with `ctest -N` **before** execution.
3. The mandatory non-rendering C++ cases are executed from the build tree:
   `TestArrayAPI`, `TestSmartPointer`, `TestNew` (Common/Core),
   `TestCleanPolyData`, `TestThreshold` (Filters/Core),
   `TestXMLWriteRead` (IO/XML). Test evidence is recorded verbatim; if a case
   cannot be discovered or fails, the build fails honestly rather than skipping.
4. An **independent** CMake consumer under `/workspace/consumer` uses only the
   freshly installed SDK (`find_package(VTK COMPONENTS ...)` plus
   `vtk_module_autoinit`), builds a sphere, runs `vtkCleanPolyData`, round-trips
the result through `vtkXMLPolyDataWriter`/`Reader`, and applies `vtkThreshold`.
It asserts point counts, the surviving `Elevation` array and a strict subset of
the cells, then prints `CONSUMER_OK`.

## Honest limitations

* Profile is **core / data-only**: no RenderingCore, no RenderingOpenGL2, no EGL,
  no offscreen render window, no image baselines. `TestOffscreenRenderingResize`
  and `TestEGLRenderWindowResize` are reference-profile tests and are not run here.
* `octree` is compiled because the VTK 9.4.2 test-dependency closure demands it; no
  rendering module is enabled as a result.
* No Python or Java wrappers are produced, so no wheel/venv consumer exists.
* The selected tests are self-contained, but VTK can pull `ExternalData` objects at
  test time. The frozen source archive ships its `.ExternalData` store; if an object
  were genuinely absent the corresponding test would fail (never silently skipped)
  because the environment is offline.
* Wall-clock and peak memory are unmeasured here; a full `run` on 4 build jobs needs
  a large share of the 3-hour budget.
* `Session.finish()` marks `independent_verified=false`; independence is asserted by
  the separate out-of-tree consumer build, not by the builder itself.
