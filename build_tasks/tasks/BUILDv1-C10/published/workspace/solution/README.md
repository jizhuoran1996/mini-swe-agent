# BUILDv1-C10 (core profile) - VTK Common/Filters/IO SDK

## What this builds

From the frozen VTK source release (commit `13acb1a5dd0ad7f7635f2511f44e599733643d06`,
v9.4.2) this builder performs a clean, out-of-source, offline CMake/Ninja build of a
**non-rendering** scientific SDK and installs it under the output tree.

Enabled modules (forced `YES`, dependencies pulled in transitively):

* `CommonCore`, `CommonDataModel`, `CommonExecutionModel`
* `FiltersCore`, `FiltersGeneral`, `FiltersSources`
* `IOLegacy`, `IOXML`
* `octree` - required leaf dependency of the test closure. With
  `VTK_BUILD_TESTING=WANT` the module scan (`CMake/vtkModule.cmake`) reaches
  `VTK::RenderingLabel` through the test dependency graph, and that module
  hard-requires `VTK::octree`. Enabling that leaf module explicitly is the
  documented fix; it does **not** enable any rendering capability - the
  Rendering group stays `DONT_WANT`.

Every non-target group (`StandAlone`, `Rendering`, `Qt`, `Web`, `Tk`, `MPI`,
`Charts`, `Views`, `Geovis`, `Infovis`, `Imaging`, `Domains`, `Interaction`) is
`DONT_WANT`, so only the requested modules and their transitive test
dependencies are scheduled. Python and Java wrapping are off. This matches the
frozen CORE profile ("Common/Filters/IO 多模块 SDK 与非渲染 C++ test suites").
Mesa/EGL offscreen rendering belongs to the **reference** profile and is not
built here.

## Offline test data

VTK registers every test baseline and fixture as an ExternalData object and
schedules the whole set as an `ALL` custom target (`VTKData`). With no network,
the default build would try to fetch baselines even though the selected
Common/Filters/IO C++ cases ship their own inputs.

This builder uses VTK's **official** supported option
`-DVTK_DATA_EXCLUDE_FROM_ALL=ON` (defined in `CMake/vtkExternalData.cmake` and
consumed in the top-level `CMakeLists.txt` as
`set_property(TARGET VTKData PROPERTY EXCLUDE_FROM_ALL 1)`). Like upstream
documents, this excludes the aggregate download target from `ninja all` while
leaving every fetch rule, `ExternalData_Add_Test` registration and baseline
hash untouched. Tests that need a fixture not present locally fail honestly;
nothing is skipped or mocked, and no upstream CMake function is monkey-patched.

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
   `TestXMLWriteRead` (IO/XML). Evidence is recorded verbatim; a missing or
   failing case aborts the build honestly rather than being skipped.
4. An **independent** CMake consumer under `/workspace/consumer` uses only the
   freshly installed SDK (`find_package(VTK COMPONENTS ...)` plus
   `vtk_module_autoinit`). It builds a sphere, runs `vtkCleanPolyData`,
   round-trips the result through `vtkXMLPolyDataWriter`/`Reader`, and applies
   `vtkThreshold`, asserting point counts, the surviving `Elevation` array and a
   strict subset of the cells before printing `CONSUMER_OK`.

## Honest limitations

* Profile is **core / data-only**: no RenderingCore, no RenderingOpenGL2, no
  EGL, no offscreen render window, no image baselines. The
  `TestOffscreenRenderingResize` / `TestEGLRenderWindowResize` cases belong to
  the reference profile and are not run here.
* `octree` is compiled solely because the VTK 9.4.2 test-dependency closure
  requires it; no rendering module is enabled as a result.
* No Python or Java wrappers are produced, so no wheel/venv consumer exists.
* `VTK_DATA_EXCLUDE_FROM_ALL=ON` keeps the aggregate data-fetch target out of
  `ninja all`. Tests whose inputs are not shipped in the frozen source archive
  would fail rather than being fetched.
* Wall-clock and peak memory are unmeasured here; a full `run` on 4 build jobs
  needs a large share of the 3-hour budget.
* `Session.finish()` marks `independent_verified=false`; independence is
  asserted by the separate out-of-tree consumer build, not by the builder
  itself.
