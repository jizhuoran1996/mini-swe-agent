# BUILDv1-F09 - LightGBM CPU CLI + native SDK from source

Builds the LightGBM v4.6.0 CPU command-line tool, its shared C-API library and
public headers from the frozen source archive, installs them to an isolated
prefix, runs the complete upstream C++ GoogleTest suite (testlightgbm, including
`ArrowChunkedArrayTest`), and then verifies the installed SDK with an independent
consumer that reloads a CLI-trained model and must reproduce the CLI predictions.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input
    python3 solution/main.py run --input input --output output --jobs 4

* `--help` prints usage without building anything.
* `doctor --input input` verifies the archive sha256, the presence of cmake,
  ninja, gcc/g++, python3, ldd, a working clang/clang++ pair with a real OpenMP
  probe, and a usable GoogleTest dependency. It exits 78 listing every missing
  item, 0 when ready.
* `run` performs: clang OpenMP probe -> cmake configure (clang/clang++,
  Release, `BUILD_CLI=ON`, `BUILD_CPP_TEST=ON`, `USE_OPENMP=ON`, GPU/CUDA/MPI
  off) -> `cmake --build` with Ninja (`BUILD_JOBS<=4`) -> `cmake --install` into
  `output/install` -> `testlightgbm --gtest_list_tests` inventory ->
  `testlightgbm --gtest_output=xml` -> compile `solution/consumer.cpp` against
  the installed headers/library -> train a short model with the installed
  `lightgbm` CLI on the official `examples/regression` data -> predict with both
  the CLI and the C-API consumer -> assert the predictions agree.

Every configure/build/install/test/consumer command goes through
`buildkit.Session`, so exit codes and complete logs are preserved under
`output/logs`, the parsed test summary comes from real gtest output, and
`install_manifest.json` / `install.tar.gz` describe only files written by this
build. All consumer artifacts (model, predictions, binary, its source) live in
`/workspace/consumer`, outside `/workspace/src`.

## Toolchain: why clang

The frozen `tests/cpp_tests/test_arrow.cpp` uses explicit template
specialisation at class scope, which GCC 13 rejects (`explicit specialization in
non-namespace scope`) but Clang accepts. The build therefore configures
`CMAKE_C_COMPILER`/`CMAKE_CXX_COMPILER` to a genuine clang/clang++ pair
(clang-18 preferred). No official test source is modified, skipped or excluded;
the full `CPP_TEST_SOURCES` list from upstream CMake is compiled.

OpenMP stays ON. Before configure, the builder probes the chosen `clang++` with
`-fopenmp` and, if that cannot link, with `-fopenmp=libgomp` (Clang's supported
runtime selector, using the GCC OpenMP runtime that ships with the image). The
working flags are passed to CMake through `OpenMP_*_FLAGS`/`OpenMP_*_LIB_NAMES`
and the resolved `libomp`/`libgomp` path, so `find_package(OpenMP REQUIRED)`
succeeds against a real runtime instead of being silently disabled.

## Consumer language

LightGBM's `include/LightGBM/c_api.h` transitively includes
`include/LightGBM/arrow.h`, which is a C++ header (`#include <algorithm>` and
`std::` templates). So a translation unit that includes `c_api.h` must be C++.
The consumer is therefore `solution/consumer.cpp`, built by the same
`clang++` that built the library, and linked against the freshly installed
`lib_lightgbm.so` with an rpath. This is upstream's public-header contract, not
an avoidance of the C API - the consumer calls only `LGBM_BoosterCreateFromModelfile`,
`LGBM_BoosterPredictForFile` and `LGBM_BoosterFree`.

## Offline GoogleTest wiring

`BUILD_CPP_TEST=ON` calls `find_package(GTest CONFIG)`, which does not reach the
multiarch config on this image, and would otherwise fall back to cloning
googletest from GitHub. When an upstream source tree (e.g. `/usr/src/googletest`)
is present the builder passes `-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=<dir>`, the
supported CMake override that makes `FetchContent` consume those local sources.
If only a `GTestConfig.cmake` exists, `-DGTEST_ROOT` is used instead. Either way
the real upstream GoogleTest is compiled here; nothing is fetched from the
network.

## Evidence emitted

* `output/logs/NNN_*.log` plus `commands.json` - every subprocess with argv, cwd and exit code
* `output/tests.json` - the executed official selector with the parsed gtest case count
* `output/cpp_tests.xml` - raw GoogleTest XML for this run
* `output/install_manifest.json`, `output/install.tar.gz` - installed bin/lib/include
* `output/consumer_verification.json` - toolchain, OpenMP implementation, row count and max abs difference between CLI and C-API predictions
* `output/run.json` - task metadata with `independent_verified=true`

## Honest limitations

* A local GoogleTest (upstream source tree or config package) and a Clang
  toolchain with a working OpenMP runtime are hard prerequisites. `doctor`
  reports each absence explicitly and `run` then fails honestly; nothing is
  fetched from the network and OpenMP is never silently downgraded.
* The C-API consumer must be compiled as C++ because LightGBM's own public
  headers require it; this mirrors upstream usage and does not alter the
  library's C ABI.
* No GPU, CUDA or MPI features are exercised; the profile is CPU/OpenMP only.
* No Python-package wheel is produced (that is the `extended` profile).
* CLI and C-API predictions are compared numerically with tolerance 1e-6, not
  byte-wise; both paths share the same C++ inference code, but text formatting
  of model files is not asserted byte-identical.
* `cmake --install` destinations follow LightGBM's own `install()` rules
  (`bin/`, `lib/`, `include/LightGBM/`); the builder does not fabricate a
  different layout.
