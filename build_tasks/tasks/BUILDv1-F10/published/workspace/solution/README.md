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
required build tools, the highest available CMake (preferring a newer tool such as the CMake
3.31 install under `/opt` when the source minimum demands it) and the offline
`/opt/wheelhouse`. It prints the exact missing items and exits **78** when not ready, **0**
when ready, and never builds anything.

`run` repeats that readiness gate first; on failure it prints the concrete missing list and
exits **78** without calling `Session.finish`. Otherwise it extracts the archive with
`Session.prepare()` and drives the upstream `build.sh`:

    build.sh --config Release --build_dir <build> --build_shared_lib --build_wheel \
      --parallel <jobs> --skip_submodule_sync --update --build --cmake_generator Ninja \
      --cmake_extra_defines onnxruntime_BUILD_UNIT_TESTS=ON \
                          FETCHCONTENT_SOURCE_DIR_<NAME>=/workspace/cache/ort_deps/<name> ...

The values handed to `--cmake_extra_defines` are raw `NAME=VALUE` tokens because ORT's own
`build.sh` prepends the `-D` for each one; passing `-DNAME=VALUE` makes `build.py`'s argparse
treat the tokens as options and abort with *expected at least one argument*.

Every prepared dependency tree is injected through the standard, legitimate CMake override
`-DFETCHCONTENT_SOURCE_DIR_<UPPERNAME>=...`, so configure never reaches the network and the
pinned FlatBuffers 23.5.26 source (not the image `flatc`) generates the ABI that is compiled.
The FetchContent names are read from the frozen `cmake/external/*.cmake` declarations (both
`FetchContent_Declare` and `onnxruntime_fetchcontent_declare` spellings) and each declared
name is matched to the prepared tree it corresponds to, tolerating the few dependencies
whose cache directory name differs from the CMake name; wrapped source trees (a single
inner directory) are resolved to their real project root. A prepared tree that has no
matching declaration is still exported under its own directory-derived variable, which is
harmless.

Then it runs the unchanged official `onnxruntime_test_all` and `onnxruntime_shared_lib_test`
with gtest XML output, stages **only** the wheel produced by this run
(`build/Release/dist`, rejecting anything below 1 MiB so a prebuilt wheel cannot be
substituted along with the `libonnxruntime.so*` built in the same tree, installs the wheel
with `--no-index --find-links /opt/wheelhouse` into a fresh `/workspace/consumer/venv`,
installs the offline consumer dependencies, and finally runs `solution/consumer_ort.py` in a
new process against a MatMul+Add+ReLU ONNX graph, asserting that `CPUExecutionProvider` is
first, that the graph inputs/outputs match, that the shipped native shared library is
present and hashed, and that CPU output agrees with an independent NumPy computation for two
different inputs.

Build parallelism is clamped to `<= 4`; test parallelism is pinned at `2`. No
`-march=native` and no unbounded link concurrency is used.

## Artifacts under `--output`

* `logs/*.log` - stdout/stderr of every build/test/install/consumer command.
* `commands.json`, `tests.json` - command index and real parsed test evidence.
* `dependency_map.json` - prepared trees, their resolved roots, the declared FetchContent
  names and the exact `FETCHCONTENT_SOURCE_DIR_*` overrides that were applied.
* `<wheel>.whl` - the wheel built by this run.
* `consumer_report.json` - module path, providers, graph hash, native library hashes, per-trial error.
* `install_manifest.json`, `install.tar.gz`, `run.json` - install tree and run record.

## Honest limitations

This frozen profile declares `submodules_ready: false` and
`offline_dependencies_ready: false`. If the mounted archive is not the modern FetchContent
release, if a dependency tree listed in `cpu_dependency_sources` is missing or empty under
the declared cache destination, if no CMake satisfies the source minimum, or if
`/opt/wheelhouse` does not carry `onnx`/`numpy`, `doctor` names those exact items and `run`
exits 78 instead of attempting a networked build. Everything downstream of that gate is
fully implemented and executes unchanged once the builder supplies the dependencies
`doctor` reports: a FetchContent declaration that has no prepared tree at all can only be
resolved by the build-time network fetch that this offline contract forbids, so no test
expectation is modified and no failing test is converted into a skip.
