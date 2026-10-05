# BUILDv1-F09 - LightGBM CPU CLI + native SDK from source

Builds the LightGBM v4.6.0 CPU command-line tool, its shared C-API library and
public headers from the frozen source archive, installs them to an isolated
prefix, runs the upstream C++ GoogleTest suite (testlightgbm), and then verifies
the installed SDK by compiling an independent C-API consumer that loads a model
trained by the newly installed CLI and reproduces its predictions.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input
    python3 solution/main.py run --input input --output output --jobs 4

* `--help` prints usage without building anything.
* `doctor --input input` checks the archive sha256, the presence of cmake, ninja,
  gcc/g++, python3, ldd, an OpenMP compile probe and a usable GoogleTest
  dependency (source tree with `CMakeLists.txt` or a config package). It exits 78
  listing every missing item, 0 when ready.
* `run` performs: cmake configure -> cmake --build (Ninja, `BUILD_JOBS<=4`) ->
  cmake --install into `output/install` -> `testlightgbm --gtest_list_tests` ->
  `testlightgbm --gtest_output=xml` -> compile `solution/consumer.c` with the
  installed headers/library -> train a short model with the installed `lightgbm`
  CLI on `examples/regression` -> predict with both the CLI and the C API consumer
  -> assert identical predictions outside the source tree.

The `buildkit.Session` helper is used for every configure/build/install/test and
consumer command, so exit codes and full logs are preserved under `output/logs`,
the test summary is parsed from real gtest output, and the install manifest and
`install.tar.gz` are produced from the files actually written by this build.
All consumer artifacts (model, predictions, compiled binary, its source) live in
`/workspace/consumer`, never inside `/workspace/src`.

## Offline GoogleTest wiring

LightGBM's `BUILD_CPP_TEST=ON` calls `find_package(GTest CONFIG)` and, if that
fails, falls back to `FetchContent` from GitHub. On the target image the
multiarch `GTestConfig.cmake` is not reached by the default CMake search path,
which would make the fallback try (and fail) to clone over the network. To keep
the build genuinely offline yet use the real upstream GTest sources, the builder
passes `-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=<system source tree>` when a source
tree such as `/usr/src/googletest` is present, so `FetchContent` resolves locally.

## Evidence emitted

* `output/logs/NNN_*.log` - every subprocess, with argv and exit code in `commands.json`
* `output/tests.json` - the executed official selector with parsed gtest case count
* `output/cpp_tests.xml` - raw GoogleTest XML for the run
* `output/install_manifest.json`, `output/install.tar.gz` - installed bin/lib/include
* `output/consumer_verification.json` - row count and max abs difference between CLI and C-API predictions
* `output/run.json` - task metadata with `independent_verified=true`

## Honest limitations

* GoogleTest must be reachable locally (a source tree with `CMakeLists.txt` such
  as `/usr/src/googletest`, or a config package). `doctor` reports the absence as
  a missing dependency and `run` fails honestly in that case; the offline build
  never fetches anything from the network.
* No GPU, CUDA or MPI features are exercised; the profile is CPU/OpenMP only.
* No Python-package wheel is produced (that is the `extended` profile).
* C API predictions are compared numerically (tolerance 1e-6), not byte-wise.
* `cmake --install` destination subdirectories follow LightGBM's own `install()`
  rules (`bin/`, `lib/`, `include/LightGBM/`); the builder does not fabricate a
  different layout.
