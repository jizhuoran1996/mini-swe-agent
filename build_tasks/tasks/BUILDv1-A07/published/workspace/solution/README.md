# BUILDv1-A07 - libevent CORE profile builder (no TLS)

The source archive, ref and commit are read from the input manifest at
runtime and the archive sha256 is verified before extraction; the frozen
contract binds `release-2.2.2-alpha`.

## CORE profile scope

* Components: `event_core`, `event_extra`, `event_pthreads` - shared **and**
  static, via `-DEVENT__LIBRARY_TYPE=BOTH`.
* TLS is deliberately **disabled** (`-DEVENT__DISABLE_OPENSSL=ON`,
  `-DEVENT__DISABLE_MBEDTLS=ON`) per the frozen core contract. This differs
  from the reference profile, which enables TLS/OpenSSL.
* Upstream tests and samples are enabled; benchmarks are disabled to shrink
  the build. The upstream `regress` suite is still registered and executed as
  part of the same single CTest pass.

## Usage

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input
    python3 solution/main.py run --input input --output output --jobs 4

* `--help` prints usage without touching the tree or building.
* `doctor --input input` prints each exact missing source archive / tool and
  exits `78` if anything required is absent, `0` when the environment is ready.
* `run` verifies the archive checksum, extracts into `/workspace/src`,
  configures with CMake, compiles with up to 4 jobs, records the CTest
  inventory (`ctest -N`), executes the complete upstream suite **once**
  (`ctest --output-on-failure -j <= TEST_JOBS`), installs to
  `output/install`, then compiles and runs the C consumer in
  `solution/consumer.c` against that fresh install, outside the source tree.

## Single authoritative test pass

The previous flow ran both the `verify` target and a full CTest pass, which
re-executed the same upstream tests. This version runs the suite exactly once
via CTest; the inventory (`ctest -N`) is a discovery pass that executes
nothing.

## Evidence and honesty

All configure/build/inventory/test/install/consumer commands go through the
`buildkit.Session`, producing `output/commands.json`, `output/tests.json`,
per-command logs, `output/install_manifest.json`, `output/install.tar.gz` and
`output/run.json` with real exit codes and raw upstream output.

Failing upstream cases are **recorded, not filtered or skipped**: if CTest
exits non-zero, the driver appends a test entry with `failed: true`, the real
log path and the real exit code, then continues the pipeline. The suite is
never re-run to mask a failure, and no expected output is modified.

## Consumer

The consumer asserts real semantics: `evthread_use_pthreads()` locking, a
`bufferevent_pair` loopback transfer, a timer-bounded `event_base_dispatch`
and ordered shutdown. It prints `CONSUMER_OK` only on success and links
against the freshly-installed prefix via `-L` / `-Wl,-rpath`, never against
any system-installed libevent.

## Honest limitations

* No TLS: `event_openssl` is intentionally omitted; no TLS consumer is run,
  and none is claimed.
* `tests.json` `parsed_count` may be `null` when the generic parser cannot
  recognise a suite's output; the complete raw upstream log is preserved and
  remains the authoritative evidence.
* The install is private to `output/install`; no system or globally-installed
  copy of libevent is ever substituted.
