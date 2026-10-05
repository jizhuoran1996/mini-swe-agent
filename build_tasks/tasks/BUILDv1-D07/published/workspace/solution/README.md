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

## doctor (corrected source-path contract)

`doctor --input <dir>` performs a cheap, real pre-flight:

* locates `manifest.json`, reads the **actual** declared source archive filename
  and SHA-256 and verifies the digest byte-for-byte;
* one-pass scans the bundle for the real required CPU paths, expressed as
  `accept` alternatives:

  - `CMakeLists.txt`, `cmake/tools.cmake`, `contrib/CMakeLists.txt`,
    `contrib/sysroot/README.md`,
  - `contrib/googletest/CMakeLists.txt`,
  - `contrib/boost-cmake/CMakeLists.txt` + `contrib/boost/boost/version.hpp`
    (Boost ships no top-level `CMakeLists.txt`; the wrapper lives under
    `contrib/boost-cmake`),
  - `contrib/openssl-cmake/CMakeLists.txt` + `contrib/openssl/Configure`
    (OpenSSL is autotools-based; the wrapper lives under `contrib/openssl-cmake`),
  - **`contrib/openssl/include/openssl/ssl.h` OR
    `contrib/openssl/include/openssl/ssl.h.in`** — `ssl.h` is *generated at
    configure time* by the official OpenSSL build from the `ssl.h.in` template,
    so the doctor accepts the genuine template when the generated output is not
    shipped in the source bundle. It never demands a build output before build,
    and never synthesizes a fake header. Accepted templates are recorded under
    `found.generated_at_configure`,
  - `contrib/zlib-ng/CMakeLists.txt`, `contrib/libarchive/CMakeLists.txt`,
  - `src/Columns/tests/gtest_column_object.cpp`;

* extracts the real `cmake_minimum_required(VERSION 3.25)` from
  `CMakeLists.txt` and the actual `CLANG_MINIMUM_VERSION` declared in
  `cmake/tools.cmake` (or a literal `VERSION_LESS` guard), and compares them to
  the probed `cmake`, `clang`/`clang++` versions — so a clang-19 requirement is
  reported as an exact missing tool, never silently faked or bypassed;
* probes `cmake`, `ninja`, `python3`, `clang`/`clang++`, `ld.lld` and
  `llvm-config` on PATH (alias aware, preferring `-19`), recording `--version`.

Exit code is `0` when the environment is genuinely ready and `78` otherwise,
with `missing[]` listing every exact source/tool/dependency gap.

## run (only proceeds when doctor is ready)

Everything is driven through the trusted `buildkit.Session` so each command's
argv/cwd/exit-code/log-digest is preserved:

1. `prepare()` — checksum-verifies the source archive and extracts it safely.
2. configure — `cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=ON
   -DENABLE_RUST=OFF -DCMAKE_C_COMPILER=<clang-19> -DCMAKE_CXX_COMPILER=<clang++-19>
   -DCMAKE_C_FLAGS=-g0 -DCMAKE_CXX_FLAGS=-g0` with `-fuse-ld=lld`. The OpenSSL
   `ssl.h` is generated from `ssl.h.in` here by the official build; nothing is
   patched or faked.  Release + `-g0` avoids the debug-info explosion while
   leaving every CPU library target and the official tests unchanged.
3. build — `cmake --build ... --parallel <jobs> --target clickhouse unit_tests_dbms`.
4. official tests — a real `--gtest_list_tests --gtest_filter=ColumnObject.*`
   inventory, then the `ColumnObject.*` execution (zero-match / all-skip is
   detected and rejected).
5. package — copy the freshly built binary into `output/install/bin/clickhouse`
   with component symlinks and license files.
6. consumer — out-of-tree `clickhouse --version`, `clickhouse local` aggregate
   over `numbers(1000)` (= `499500`, `1000` rows), and a JSON-column round-trip.
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
  is used and a note is recorded.
* Rust optional components stay disabled per the frozen CPU profile
  (`-DENABLE_RUST=OFF`).
* No system ClickHouse, package-manager build, or prebuilt artifact is used as a
  delivered target. `install/` contains only files produced this session.
