# BUILDv1-D07 — ClickHouse core build & qualification driver

Driver for the **core** profile of the ClickHouse build task: compile the full
`clickhouse` monolith and the aggregated `unit_tests_dbms` binary from the pinned
source release (`v25.3.3.42-lts`, commit `c4bfe68b...`), run the official
`ColumnObject.*` GoogleTest suite, stage the freshly built binary into a private
install tree, and consume it with `clickhouse local`.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input /workspace/input
python3 solution/main.py run --input input --output output --jobs 4
```

`--help` is pure argparse and needs no build. `run` refuses to start unless
`doctor` is ready.

## doctor

`doctor --input <dir>` performs a cheap, real pre-flight:

* locates `manifest.json`, reads the **actual** declared source archive filename
  and SHA-256 (post-restore the manifest points at the full
  `source-with-submodules.tar.gz` bundle with its real digest);
* one-pass scans the bundle for the required CPU paths
  (`CMakeLists.txt`, `cmake/tools.cmake`, `contrib/CMakeLists.txt`,
  `contrib/sysroot/README.md`, `contrib/googletest/CMakeLists.txt`,
  `contrib/boost/...`, `contrib/zlib-ng/...`, `contrib/openssl/...`,
  `contrib/libarchive/...`, `src/Columns/tests/gtest_column_object.cpp`);
* extracts the top-level `cmake_minimum_required(VERSION X)` from
  `CMakeLists.txt` and the minimum `CMAKE_CXX_COMPILER_VERSION VERSION_LESS Y`
  guard from `cmake/tools.cmake`, then compares them against the locally probed
  `cmake` and `clang`/`clang++` versions — so a clang-19 requirement is reported
  as an **exact missing tool**, never silently faked;
* probes `cmake`, `ninja`, `python3`, `clang`, `clang++`, `ld.lld` on PATH
  (alias aware) and records their `--version` first line.

Exit code is `0` when the environment is genuinely ready and `78` otherwise,
with `missing[]` listing every exact source/tool/dependency gap. No claim of
readiness is made when the environment is not verified.

## run (only proceeds when doctor is ready)

Everything is driven through the trusted `buildkit.Session` so each command's
argv/cwd/exit-code/log-digest is preserved:

1. `prepare()` — checksum-verifies the source archive and extracts it safely.
2. configure — `cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=ON
   -DENABLE_RUST=OFF -DCMAKE_C_FLAGS=-g0 -DCMAKE_CXX_FLAGS=-g0` with the discovered
   Clang/Clang++. Release + `-g0` avoids the debug-info explosion while leaving
   every CPU library target and official test unchanged; the 24 GiB workspace
   guard would otherwise trip on `RelWithDebInfo` debug sections.
3. build — `cmake --build ... --parallel <jobs> --target clickhouse unit_tests_dbms`.
4. official tests — first `unit_tests_dbms --gtest_list_tests --gtest_filter=ColumnObject.*`
   captures the real inventory, then `unit_tests_dbms --gtest_filter=ColumnObject.*`
   executes it (a zero-match / all-skip run is detected and rejected).
5. package — copy the freshly built binary into `output/install/bin/clickhouse`
   with component symlinks and license files.
6. consumer — out-of-tree `clickhouse --version`, `clickhouse local` aggregate
   over `numbers(1000)` (= `499500`, `1000` rows), and a JSON-column round-trip
   asserted semantically.
7. `finish()` — writes `install_manifest.json`, `install.tar.gz`, `commands.json`,
   `tests.json`, `run.json`.

`--jobs` is always clamped to `<= 4` (`BUILD_JOBS`); a single aggregated gtest
binary runs (`TEST_JOBS <= 2`). No `-march=native`, no unbounded fuzzing, no
network, no sudo, no host modifications.

## Honest limitations

* Building the full ClickHouse monolith plus `unit_tests_dbms` is a **very large**
  C++ graph; on a 4-way build it is not guaranteed to finish inside 3 hours. The
  driver does not fake this — it either produces the real binary or fails honestly.
* The core profile intentionally stops at `clickhouse local`; no persistent
  `clickhouse-server`/`clickhouse-client` acceptance is attempted (that is the
  reference-profile extension).
* `ld.lld` is desirable but not mandatory; when absent the Clang default linker
  is used and a note is recorded in the doctor report.
* No system ClickHouse, package-manager build, or prebuilt artifact is used as a
  delivered target. `install/` contains only files produced this session.
