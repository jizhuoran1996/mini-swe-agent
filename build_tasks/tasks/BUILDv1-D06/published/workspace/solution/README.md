# BUILDv1-D06 (core profile): Arrow C++ core/IPC SDK

Builds the Apache Arrow C++ columnar SDK from the pinned source archive
`apache-arrow-19.0.1` (commit `272715f6df2a042d69881ffa03d5078c58e4b345`),
runs the official `arrow-ipc-read-write-test` CTest entry, installs the SDK
and verifies it from a CMake consumer built **outside** the source tree.

## Usage

```sh
python3 solution/main.py doctor --input input      # exit 0 ready / 78 missing
python3 solution/main.py run --input input --output output --jobs 4
```

`run` performs: `Session.prepare()` (sha256-verified extraction into
`/workspace/src`) -> CMake/Ninja configure (`ARROW_BUILD_TESTS=ON`,
`ARROW_IPC=ON`, compute/CSV/Parquet/dataset off, `ARROW_DEPENDENCY_SOURCE=SYSTEM`)
-> build -> `cmake --install` into `<output>/install` -> build the official
test target -> `ctest -N` inventory -> `ctest -R '^arrow-ipc-read-write-test$'`
-> consumer configure/build/run under `/workspace/consumer`.

The consumer creates a 4-row table with int32/utf8/float64 columns containing
nulls, writes an Arrow IPC file through the installed SDK and re-reads it,
asserting schema, row order, null positions and values. It fails loudly if any
check is wrong.

## Honest limitations

- The core profile deliberately differs from the full reference scope: compute,
  CSV, Parquet, dataset, Flight, S3/GCS, CUDA and Gandiva are **not** built.
  Only `arrow-ipc-read-write-test` is executed as official test evidence.
- The build uses `ARROW_DEPENDENCY_SOURCE=SYSTEM`; the host must provide
  flatbuffers (with `flatc`), rapidjson and gtest development files. If any are
  absent, `doctor` exits 78 and `run` fails at configure time — nothing is
  silently substituted.
- `arrow-testing` / `parquet-testing` submodules are not present in the archive;
  the IPC read-write test does not depend on those fixture trees, but external
  fixture-based tests would need them.
- No prebuilt Arrow libraries are used or accepted; the delivered SDK is the
  result of this source build only.
