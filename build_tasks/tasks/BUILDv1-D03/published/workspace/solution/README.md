# BUILDv1-D03 (core profile) - Redis source build, official string unit, plain local consumer

Builds Redis 7.4.5 (`7e0f53393290f7c1f35596117b67748efad16580`) from the frozen
source archive **without TLS** (`BUILD_TLS` is deliberately not set), installs it
into a private prefix, runs the official Tcl unit `unit/type/string`, and then
consumes the freshly installed binaries from outside the source tree.

## Usage

```bash
python3 solution/main.py --help                 # no build, prints usage
python3 solution/main.py doctor --input input   # exit 0 ready / exit 78 missing items
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` lists the exact missing items (input manifest/archive, archive sha256,
required source paths inside the archive, `make`, a C compiler, `tclsh >= 8.5`).
It exits 78 when anything required is absent and 0 when the core build can start.

## What `run` does

1. `buildkit.Session.prepare()` verifies the archive sha256 and extracts it to `/workspace/src`.
2. `make -j<BUILD_JOBS>` (BUILD_JOBS <= 4) at the source root: core server, CLI,
   benchmark and check tools with the bundled jemalloc, no TLS.
3. `make PREFIX=/workspace/output/install install`, then the installed
   `redis-server --version` is recorded.
4. A fixed no-TLS config is installed at `install/etc/redis-core.conf`.
5. Official discovery `./runtest --list-tests` is saved verbatim to
   `official_test_inventory.txt` and must contain `unit/type/string`.
6. A test port base is chosen from a **low, non-ephemeral range** (15000-32000)
   after verifying that the whole contiguous window the harness needs
   (`baseport - 40` .. `baseport + portcount + 24`) can be bound simultaneously.
   The chosen base is recorded in `official_test_baseport.json`. This avoids the
   ephemeral-port (32768-60999) collisions that can make the Tcl harness abort
   with `Can't find a non busy port`.
7. Official execution: `./runtest --single unit/type/string --clients <TEST_JOBS>
   --baseport <verified base> --portcount 16` (TEST_JOBS <= 2). The raw log is
   kept, and `official_test_report.json` records the upstream `[ok]` assertion
   count plus the upstream `All tests passed without errors` marker.
8. Consumer verification outside the source tree (`/workspace/consumer`): starts
   the installed `redis-server` on 127.0.0.1 with AOF enabled, drives it with the
   installed `redis-cli` and with a hand written RESP client (SET/APPEND/STRLEN,
   HSET/HGET, MULTI/EXEC, and two expected error paths: INCR on a non-integer
   string and GET on a hash), snapshots a SHA-256 data digest, performs a graceful
   `SHUTDOWN`, restarts the same server and asserts the digest is unchanged via AOF.
9. `Session.finish()` writes `install_manifest.json`, `install.tar.gz` and `run.json`.

The consumer script is generated from the template embedded in `main.py`; an
identical copy is shipped at `solution/consumer/verify_core.py` for review.

## Honest limitations

* Core profile only: no TLS is compiled, so TLS ports, TLS certificates and the
  reference-profile TLS consumer are explicitly out of scope.
* Only the official `unit/type/string` Tcl unit is executed (that is the frozen
  core selection). The AOF integration unit, cluster, module and sentinel suites
  are not run and are not claimed.
* Assertion counts come from the upstream `[ok]` lines; the Redis Tcl harness does
  not emit a single machine-readable case total, so no case count is invented.
* Ports are bound dynamically per run; timestamps, PIDs and archive metadata are
  not expected to be reproducible, only the functional results are.
* No network access, no sudo and no system-wide installation are used; everything
  is written under `/workspace` and `/tmp`.
