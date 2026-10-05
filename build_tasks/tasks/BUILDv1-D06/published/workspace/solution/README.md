# BUILDv1-D06 (core profile): Arrow C++ core/IPC SDK

Builds the Apache Arrow C++ columnar SDK from the pinned source archive
`apache-arrow-19.0.1` (commit `272715f6df2a042d69881ffa03d5078c58e4b345`),
runs the official `arrow-ipc-read-write-test` CTest entry, installs the SDK and
verifies it from a CMake consumer built **outside** the source tree.

## Usage

```sh
python3 solution/main.py doctor --input input      # exit 0 ready / 78 missing
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` probes the source archive, the toolchain (`cmake`, `ninja`, `c++`,
`cc`, `flatc`, `pkg-config`) and the development headers for `flatbuffers`,
`rapidjson` and `gtest`. It reports the exact missing item list and exits `78`
when anything is absent. It additionally reports whether a genuine `re2`
(header + linkable library or a CMake package config) is available.

`run` re-checks the inventory before touching the source tree, then performs
`Session.prepare()` (sha256-verified extraction into `/workspace/src`) ->
CMake/Ninja configure -> build of the official test target -> `cmake --install`
into `<output>/install` -> `ctest -N` inventory ->
`ctest -R '^arrow-ipc-read-write-test$'` -> consumer configure/build/run under
`/workspace/consumer`.

## Component selection is honest and detected, not assumed

Arrow's CMake **aborts** configuration when a required third-party package is
missing. The run therefore determines the real component set from the host:

- The optional `compute` module is enabled **only** when a genuine `re2`
  provider is found (`include/re2/re2.h` plus a linkable `libre2.*`, or a
  `re2Config.cmake`); in that case `RE2_INCLUDE_DIR`/`RE2_LIB` (and `re2_DIR`)
  are passed so Arrow's own `Findre2Alt` resolves it.
- Otherwise it configures the frozen **core + IPC** scope only
  (`ARROW_COMPUTE=OFF`, `ARROW_WITH_RE2=OFF`).

CMake is given a `CMAKE_PREFIX_PATH` built from every real install prefix under
`/opt`, `/workspace/cache`, `/usr/local` and `/usr` (including staged locations
such as `/opt/xsimd`), so genuine dependencies are discovered through their own
metadata.

If configuration still fails, the run raises the **real** configure log tail
(including the exact `Could NOT find ...` line) instead of a synthesized
message.

## Consumer

The consumer creates a 4-row table with int32/utf8/float64 columns containing
nulls, writes an Arrow IPC file through the freshly installed SDK and re-reads
it, asserting schema, row order, null positions and values. It links against
`Arrow::arrow_shared` from the install tree only.

## Honest limitations

- CSV, Parquet, dataset, Flight, S3/GCS, CUDA and Gandiva are **not** built in
  the core profile. Only `arrow-ipc-read-write-test` is executed as official
  test evidence.
- The build uses `ARROW_DEPENDENCY_SOURCE=SYSTEM`; no package is downloaded and
  no prebuilt Arrow library is accepted. A missing tool/dependency makes
  `doctor`/`run` exit `78` with the exact item rather than silently substituting
  a system Arrow or skipping the test.
- When no genuine `re2` is present the SDK is delivered without the optional
  compute module; this is reported in `run.json` rather than hidden.
