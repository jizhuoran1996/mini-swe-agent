# BUILDv1-D04 -- RocksDB static SDK (core profile)

Builds the frozen RocksDB v10.2.1 source (`4b2122578e475cb88aef4dcf152cccd5dbf51060`) into a
**static** SDK, runs the official `db_basic_test` binary, installs headers/library, and verifies
an out-of-tree static consumer that writes, reopens, reads and deletes keys.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` returns `78` when a blocking source/tool/dependency item is missing and `0` when the
environment is ready. `--help` never performs a build.

## Build mode (important)

Upstream RocksDB removes `SyncPoint` (and several `DBImpl::TEST_*` helpers) from the headers when
`-DNDEBUG` is defined, so the official `db_basic_test` translation unit **cannot compile** in a
`DEBUG_LEVEL=0` build. The SDK is therefore built in an assert-enabled mode (`DEBUG_LEVEL=1`, or
the upstream default / `DEBUG_LEVEL=2`) chosen at run time:

* `make -n <flags> db/db_basic_test.o` dry-run probes show whether each candidate mode passes
  `-DNDEBUG`; the first mode that provably does not is selected. Probe verdicts are recorded in
  `output/build_mode.json` together with the real build attempts.
* If a mode still fails to build, the tree is `make clean`-ed and the next candidate is tried; two
  modes are never mixed in the same tree.
* Library, test binary and install all use the *same* variables, and `PORTABLE=1` is always set so
  `-march=native` is never used.

## What `run` does

1. `Session.prepare()` verifies the source archive sha256 and extracts it to `/workspace/src`.
2. `make -j4 PORTABLE=1 <mode> static_lib db_basic_test`.
3. `output/post_build_state.json` records the archive the build actually produced (searched for,
   not assumed) and the test binary size.
4. `./db_basic_test --gtest_list_tests` -- the official inventory is stored in
   `output/discovery_db_basic_test.json` *before* any test executes.
5. `./db_basic_test` with `TEST_TMPDIR` pinned to `/workspace/build/test_tmp` (never `/dev/shm`).
6. `make <mode> PREFIX=<INSTALL_ROOT> INSTALL_PATH=<INSTALL_ROOT> install-headers install-static`
   (target names read from the upstream `Makefile`). If those targets place nothing, the built
   archive/headers are staged directly from the source tree -- `output/install_notes.json` records
   the make exit code, the exact log path, which path was used, and the archive it was staged from.
7. The consumer in `solution/consumer.cc` is compiled **only** with `<INSTALL_ROOT>/include` and
   `<INSTALL_ROOT>/lib/librocksdb.a`, linked with the `-l` set recorded in `make_config.mk`.
   `ldd` output is checked to prove no system `librocksdb` is involved.
8. Four separate consumer processes (`write`, `verify`, `delete`, `final`) prove batch writes,
   reopen durability across process boundaries, iteration counts and delete persistence.

## Scope (core profile)

* Included: static library, installed headers, `db_basic_test`, static consumer.
* Not included (reference/extended profiles only): `shared_lib`, `table_test`, Java/JNI,
  `db_bench`, cross-host or production deployment.

## Honest limitations

* Only `db_basic_test` is executed; `table_test` and the shared library are out of the frozen core
  scope, so `features.shared_lib` and `features.table_test` are reported as `false`.
* Because the official test binary requires an assert-enabled build, the delivered static library
  is built with assertions enabled (optimized, but not `-DNDEBUG`). A pure `-DNDEBUG` release
  library cannot compile the required official test in this upstream revision.
* Compression support depends on which `*-dev` packages exist in the image; RocksDB auto-detects
  them and the consumer link uses exactly the flags the build recorded. Missing optional
  compression headers are reported by `doctor` but are not blocking.
* Static linking needs extra system libraries (threads, dl, rt and the detected compression
  libraries); these are explicit in the consumer link command and logged.
* The `pkg-config` file is **builder-generated** (upstream's Makefile ships none). That is stated in
  `output/install_notes.json` and in the file itself.
* The archive name is discovered (`librocksdb.a` first, then a bounded recursive search) rather than
  assumed; if the upstream install targets place nothing, direct staging is used and recorded.
* Installed file hashes, test counts and timings are recorded from this run only; they are not
  claimed to be byte-for-byte reproducible across runs.
