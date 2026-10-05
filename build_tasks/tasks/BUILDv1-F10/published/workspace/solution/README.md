# BUILDv1-F10 -- ONNX Runtime CPU wheel + native runtime

Builds the frozen ONNX Runtime release (`release_ref` `v1.21.1`) from source into a CPU
wheel plus shared library, runs the unchanged official upstream C++ tests, then installs
and consumes the freshly built wheel from a separate virtual environment outside the
source tree.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

`--help` performs no build and does not touch the source tree.

`doctor --input INPUT` reads the mounted `manifest.json` (never a hardcoded release hash),
verifies the frozen `source.tar.gz` against `source.sha256`, streams the tarball to confirm
the real FetchContent layout (`cmake/deps.txt`, `cmake/CMakeLists.txt`, `build.sh`,
`setup.py`) and to read the actual `cmake_minimum_required`, checks every declared
`cpu_dependency_sources` tree under the prepared dependency cache
(`dependency_caches[].destination`, normally `/workspace/cache/ort_deps/<name>`), checks the
required build tools, resolves the newest real CMake on the host (globbing `/opt/cmake-*`
etc. with the `glob` module rather than `Path.glob`, which rejects absolute patterns), and
falls back to the official CMake wheel in the offline `/opt/wheelhouse` when the system
CMake is older than the source minimum. It also lists which required wheels the offline
wheelhouse actually provides (`numpy`, `protobuf`, `onnx`, `setuptools`, `packaging`). It
prints the exact missing items and exits **78** when not ready, **0** when ready, and never
builds anything.

`run` repeats that readiness gate first; on failure it prints the concrete missing list and
exits **78** without calling `Session.finish`. Otherwise it extracts the archive with
`Session.prepare()`, then performs, all through logged `buildkit` subprocesses:

1. **Builder interpreter.** A dedicated venv is created from the genuine preinstalled
   build interpreter (`/opt/buildvenv/bin/python`, falling back to `sys.executable`) and
   populated *offline* from `/opt/wheelhouse` with NumPy, setuptools, packaging, wheel and
   the source `requirements.txt` entries that exist as wheels. `doctor`/`run` never point
   CMake at a bare system Python: the previous failure was `Python::NumPy` not found
   because the driver defaulted to `/usr/bin/python3`, which has no NumPy. The run then
   proves real headers by printing `sysconfig`/`numpy.get_include()` and compiling a tiny
   `#include <Python.h>` + `#include <numpy/arrayobject.h>` translation unit with g++
   (`builder_interpreter.json` records the exact paths and version).
2. **CMake.** Uses a real system CMake when it satisfies the source minimum, otherwise
   installs the official CMake wheel (3.31.x) from the offline wheelhouse into
   `/workspace/output/toolvenv` and verifies the resulting binary's reported version.
3. **Dependency injection.** Every prepared tree under
   `/workspace/cache/ort_deps/<name>` is injected with the standard, legitimate
   `-DFETCHCONTENT_SOURCE_DIR_<UPPERNAME>=...` override, so configure never reaches the
   network and the pinned FlatBuffers 23.5.26 source (not the image `flatc`) generates the
   ABI that is compiled. FetchContent names are read from the frozen
   `cmake/external/*.cmake` declarations (both `FetchContent_Declare` and
   `onnxruntime_fetchcontent_declare` spellings) and matched to the prepared trees,
   tolerating the few dependencies whose cache directory name differs from the CMake name,
   and resolving single-directory wrapped trees to their real project root. `cmake/deps.txt`
   is never edited.
4. **Build.**

       build.sh --config Release --build_dir <build> --build_shared_lib --build_wheel \
         --parallel <jobs> --skip_submodule_sync --update --build --cmake_generator Ninja \
         --cmake_extra_defines onnxruntime_BUILD_UNIT_TESTS=ON \
                             Python_EXECUTABLE=<builder venv>/bin/python \
                             Python3_EXECUTABLE=<builder venv>/bin/python \
                             FETCHCONTENT_SOURCE_DIR_<NAME>=/workspace/cache/ort_deps/<name> ...

   The `--cmake_extra_defines` values are raw `NAME=VALUE` tokens because ORT's own
   `build.sh` prepends the `-D` for each one; passing `-DNAME=VALUE` makes `build.py`'s
   argparse treat the tokens as options and abort with *expected at least one argument*.
   The builder venv's `bin` directory leads `PATH`, so the `python3` that `build.sh`
   launches *is* the NumPy-carrying interpreter (`build.py` sets `Python_EXECUTABLE` from
   `sys.executable`); the explicit defines are a belt-and-braces duplicate with the same
   value. `PIP_NO_INDEX`/`PIP_FIND_LINKS` keep any pip subprocess offline.
5. **Official tests.** The unchanged `onnxruntime_test_all` and
   `onnxruntime_shared_lib_test` are executed from the build directory with gtest XML
   output and `LD_LIBRARY_PATH` pointed at this build's `libonnxruntime.so`.
6. **Package.** Only the wheel produced by this run (`build/Release/dist`) is staged, and
   only if it postdates the session start, exceeds 1 MiB, and actually contains this
   build's `onnxruntime/capi/onnxruntime_pybind11_state*.so` -- a prebuilt or metadata-only
   wheel cannot satisfy those checks. The `libonnxruntime.so*` from the same tree are
   staged alongside it.
7. **Independent consumption.** A fresh venv (no system site packages) is created, the
   new wheel is installed with `--no-index --find-links /opt/wheelhouse --no-deps`, and its
   real `Requires-Dist` names that exist in the wheelhouse (plus `onnx`) are installed.
   `solution/consumer_ort.py` then runs as a new process against a MatMul+Add+ReLU ONNX
   graph, asserting that `CPUExecutionProvider` is first, that the graph inputs/outputs
   match, that the shipped native shared library is present and hashed, and that CPU output
   agrees with an independent NumPy computation for two different inputs.

Build parallelism is clamped to `<= 4`; test parallelism is pinned at `2`. No
`-march=native` and no unbounded link concurrency is used.

## Artifacts under `--output`

* `logs/*.log` - stdout/stderr of every build/test/bootstrap/install/consumer command.
* `commands.json`, `tests.json` - command index and real parsed test evidence.
* `builder_interpreter.json` - builder venv, NumPy version, include paths, header probe.
* `dependency_map.json` - prepared trees, resolved roots, declared FetchContent names and
  the exact `FETCHCONTENT_SOURCE_DIR_*` overrides that were applied.
* `<wheel>.whl` - the wheel built by this run.
* `consumer_report.json` - module path, providers, graph hash, native library hashes, per-trial error.
* `install_manifest.json`, `install.tar.gz`, `run.json` - install tree and run record.

## Honest limitations

This frozen profile declares `submodules_ready: false` and
`offline_dependencies_ready: false`. If the mounted archive is not the modern FetchContent
release, if a dependency tree listed in `cpu_dependency_sources` is missing or empty under
the declared cache destination, if neither the host nor the offline wheelhouse provides a
CMake meeting the source minimum, or if `/opt/wheelhouse` lacks `numpy`/`protobuf`/`onnx`/
`setuptools`/`packaging`, `doctor` names those exact items and `run` exits 78 instead of
attempting a networked build. A FetchContent declaration with no prepared tree at all can
only be resolved by the build-time network fetch this offline contract forbids; in that
case no test expectation is modified and no failing test is converted into a skip.
Consumer dependencies that are absent from the wheelhouse are recorded in `run.json` under
`consumer_deps_not_in_wheelhouse` rather than being silently assumed present.
