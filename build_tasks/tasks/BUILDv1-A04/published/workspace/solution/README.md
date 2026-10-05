# BUILDv1-A04 - curl HTTPS client development package (core profile)

Builds upstream curl `release_ref=curl-8_14_1` (commit
`fdb8a789d2b446b77bd7cdd2eff95f6cbc814cf4`) from the frozen source archive with
the OpenSSL TLS backend, the CLI, and both shared and static libcurl.

## Usage

```
python3 solution/main.py doctor --input /workspace/input
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` lists the exact missing source/tool/dependency items and exits `78` when
anything is absent, `0` when ready. `--help` works without a build.

## What `run` does

1. Verifies the source archive sha256 and extracts it to `/workspace/src`.
2. CMake configure with `-DCURL_USE_OPENSSL=ON`, `BUILD_TESTING=ON`,
   shared + static libcurl, CLI enabled, and `CMAKE_INSTALL_RPATH` pointing at
   the private install lib directories.
3. Builds the library and CLI (`--parallel 4`, capped at BUILD_JOBS<=4).
4. Builds the official `testdeps` target.
5. Installs into the private prefix.
6. `ldd` on the freshly installed CLI confirms it resolves against the private
   libcurl (`ldd_new_cli.txt`); the run aborts otherwise, so the new client can
   never silently bind to an older system `libcurl`.
7. Records `curl -V` and requires the `OpenSSL` TLS backend to be present.
8. Runs the frozen core official test selection (test1 HTTP GET, test2 GET +
   Basic auth, test3 POST) by invoking the exact upstream harness
   `tests/runtests.pl -v 1 2 3` directly, with `CURL`, `TFLAGS` and
   `LD_LIBRARY_PATH` bound to the freshly built tree. The upstream CMake
   `tests` target is deliberately not relied on because it can return 0 with an
   empty captured log; the direct harness invocation produces real per-test
   verbose output, and the chosen command, raw log and parsed summary are
   recorded (`official_test_summary.json`, `tests.json`, `logs/`).
9. Compiles an independent C libcurl consumer outside the source tree and runs
   it against a freshly spawned local HTTP server (GET, redirect-follow, POST),
   plus a negative connection-refused case.

Every execution of a newly built binary (curl CLI, consumer, driver) is
performed with `LD_LIBRARY_PATH` including the private install lib directory.

## Honest limitations

- The core profile deliberately selects test1/2/3 only; the wider reference
  scope (`TFLAGS="HTTP HTTPS file"`) is not part of this profile.
- The upstream Perl `runtests.pl` harness does not emit a numeric pass-count in
  a form the shared parser recognizes, so `tests.json` carries
  `parsed_count: null`; the full verbose raw log is preserved and an honest
  summary (`TESTDONE` reported tests, parsed `...OK` lines) is recorded
  alongside it rather than a manufactured case count.
- The local consumer exercises loopback HTTP with the delivered libcurl; no
  public network access is used or required.
