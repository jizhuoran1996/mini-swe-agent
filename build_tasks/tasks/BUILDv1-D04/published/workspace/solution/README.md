# BUILDv1-D04 -- RocksDB static SDK (core profile)

Builds the frozen RocksDB v10.2.1 source (`4b2122578e475cb88aef4dcf152cccd5dbf51060`) into a
**static** SDK, runs the official `db_basic_test` gtest binary, installs headers/library, and
verifies an out-of-tree static consumer that writes, reopens, reads and deletes keys.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` returns `78` when a blocking source/tool/dependency item is missing and `0` when the
environment is ready. `--help` never performs a build.

## What `run` does

1. `Session.prepare()` verifies the source archive sha256 and extracts it to `/workspace/src`.
2. `make -j4 DEBUG_LEVEL=0 static_lib db_basic_test` in the source tree.
3. `./db_basic_test --gtest_list_tests` -- the official inventory is stored in
   `output/discovery_db_basic_test.json` *before* any test executes.
4. `./db_basic_test` with `TEST_TMPDIR` pinned to `/workspace/build/test_tmp` (not `/dev/shm`).
5. `make DEBUG_LEVEL=0 PREFIX=<INSTALL_ROOT> install-headers install-static` (the exact target
   names are read from the upstream `Makefile`; a documented copy fallback exists if the upstream
   install target does not place files).
6. The consumer in `solution/consumer.cc` is compiled **only** with `<INSTALL_ROOT>/include` and
   `<INSTALL_ROOT>/lib/librocksdb.a`, linked with the `-l` set recorded in `make_config.mk`.
   `ldd` output is checked to prove no system `librocksdb` is involved.
7. Four separate consumer processes (`write`, `verify`, `delete`, `final`) prove batch writes,
   reopen durability across process boundaries, iteration counts and delete persistence.

## Scope (core profile)

* Included: static library, installed headers, `db_basic_test`, static consumer.
* Not included (reference/extended profiles only): `shared_lib`, `table_test`, Java/JNI,
  `db_bench`, cross-host or production deployment.

## Honest limitations

* Only `db_basic_test` is executed; `table_test` and the shared library are out of the frozen
  core scope, so `features.shared_lib` and `features.table_test` are reported as `false`.
* Compression support depends on which `*-dev` packages exist in the image; RocksDB auto-detects
  them and the consumer link uses exactly the flags the build recorded. Missing optional
  compression headers are reported by `doctor` but are not blocking.
* Static linking requires the extra system libraries (threads, dl, rt and any detected
  compression libraries); these are made explicit in the consumer link command and logged.
* Installed file hashes, test counts and timings are recorded from this run only; they are not
  claimed to be byte-for-byte reproducible across runs.
