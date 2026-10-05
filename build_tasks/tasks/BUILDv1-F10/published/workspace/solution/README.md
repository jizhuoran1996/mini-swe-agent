# BUILDv1-F10 -- ONNX Runtime CPU wheel + native runtime

Builds the frozen ONNX Runtime release (`release_ref` `v1.21.1`) from source into a CPU
wheel plus shared library, runs the official upstream C++ tests, then installs and
consumes the freshly built wheel from a separate virtual environment outside the source
tree.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

`--help` performs no build and does not touch the source tree.

`doctor --input INPUT` reads the mounted `manifest.json` (never a hardcoded release hash),
verifies the frozen `source.tar.gz` against `source.sha256`, streams the tarball to confirm
the modern FetchContent layout (`cmake/deps.txt`, `cmake/CMakeLists.txt`, `build.sh`,
`setup.py`) and to read the real `cmake_minimum_required`, checks each declared
`cpu_dependency_sources` entry against the prepared dependency cache
(`dependency_caches[].destination`, normally `/workspace/cache/ort_deps/<name>`), checks the
required build tools and the highest available CMake against the source minimum, and checks
the offline `/opt/wheelhouse`. It prints the exact missing items and exits **78** when not
ready, **0** when ready, and never builds anything.

`run` repeats that readiness gate first; on failure it prints the concrete missing list and
exits **78** without calling `Session.finish`. Otherwise it extracts the archive with
`Session.prepare()`, then drives the upstream `build.sh`:

    build.sh --config Release --build_dir <build> --build_shared_lib --build_wheel \
      --parallel <jobs> --skip_submodule_sync --update --build --cmake_generator Ninja \
      --cmake_extra_defines onnxruntime_BUILD_UNIT_TESTS=ON \
                          FETCHCONTENT_SOURCE_DIR_<NAME>=/workspace/cache/ort_deps/<name> ...

Every prepared dependency tree is injected as `-DFETCHCONTENT_SOURCE_DIR_<UPPERNAME>=...`
(the FetchContent declaration names are read from the frozen `cmake/external/*.cmake`), so
configure never reaches the network; the pinned FlatBuffers/Protobuf/ONNX sources in the
cache are the ones that generate the ABI actually compiled. The `-D` prefix style is
detected from `tools/ci_build/build.py`, with a single guarded retry using the other
convention if the configure stage rejects the tokens.

Then it runs the unchanged official `onnxruntime_test_all` and `onnxruntime_shared_lib_test`
with gtest XML output, stages **only** the wheel produced by this run
(`build/Release/dist`, rejecting anything below 1 MiB so a prebuilt wheel cannot be
substituted), installs it with `--no-index --find-links /opt/wheelhouse` into a fresh
`/workspace/consumer/venv`, installs the offline consumer dependencies, and finally runs
`solution/consumer_ort.py` in a new process against a MatMul+Add+ReLU ONNX graph, asserting
that `CPUExecutionProvider` is first, that the graph inputs/outputs match, that the shipped
native shared library is present and hashed, and that CPU output agrees with an independent
NumPy computation for two different inputs.

Build parallelism is clamped to `<= 4`; test parallelism is pinned at `2`. No
`-march=native` and no unbounded link concurrency is used.

## Artifacts under `--output`

* `logs/*.log` - stdout/stderr of every build/test/install/consumer command.
* `commands.json`, `tests.json` - command index and real parsed test evidence.
* `dependency_map.json` - prepared dependency trees and the FetchContent names they map to.
* `<wheel>.whl` - the wheel built by this run.
* `consumer_report.json` - module path, providers, graph hash, native library hashes, per-trial error.
* `install_manifest.json`, `install.tar.gz`, `run.json` - install tree and run record.

## Honest limitations

This frozen profile declares `submodules_ready: false` and
`offline_dependencies_ready: false`. If the mounted archive is not the modern FetchContent
release, if a dependency tree listed in `cpu_dependency_sources` is missing or empty under
the declared cache destination, or if `/opt/wheelhouse` does not carry `onnx`/`numpy`,
`doctor` names those exact items and `run` exits 78 instead of attempting a networked build.
Everything downstream of that gate is fully implemented and executes unchanged once the
builder supplies the dependencies `doctor` reports. No test expectation is modified and no
falling test is converted into a skip.
