# PCRE2 core-profile builder

Builds the **CORE** profile of PCRE2 10.46 from the pinned source archive and
produces an install tree plus independent consumer evidence.

## Frozen scope (core)

| Feature | State |
|---|---|
| `PCRE2_BUILD_PCRE2_8` | ON (8-bit library, static) |
| `PCRE2_BUILD_PCRE2_16/32` | OFF (reference-only scope) |
| `PCRE2_SUPPORT_JIT` | OFF (sljit submodule deliberately not required) |
| `PCRE2_SUPPORT_UNICODE` | ON |
| POSIX wrapper (`libpcre2-posix`) | ON |
| `pcre2grep` | ON |
| Official source tests | ON, run through CTest |

## Usage

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input
    python3 solution/main.py run --input input --output output --jobs 4

* `--help` prints argument help and performs no build.
* `doctor` verifies the source archive checksum/size and the presence of
  `cc`, `cmake` and `ninja`. It prints the exact missing items and returns 78
  when anything is missing, 0 when the environment is ready.
* `run` extracts the source to `/workspace/src`, configures/builds in
  `/workspace/build`, executes the official CTest suites (aggregate plus one
  run per discovered selector), installs to `<output>/install`, and then
  compiles/runs independent consumers under `/workspace/consumer`.

## Artifacts and evidence (under `--output`)

* `install/` – `include/pcre2.h`, `include/pcre2posix.h`,
  `lib/libpcre2-8.a`, `lib/libpcre2-posix.a`, `bin/pcre2grep`, docs.
* `install.tar.gz`, `install_manifest.json` – installed-file inventory with
  sizes and sha256 digests.
* `commands.json`, `tests.json` – every build/test/consumer command with
  argv, working directory, exit code, wall time and log digest.
* `official_test_inventory.txt` – raw output of `ctest -N` captured before
  execution.
* `logs/` – full stdout/stderr for every command.

## Independent consumers

* `consumer8.c` – 8-bit API: reports `PCRE2_CONFIG_VERSION`, `JIT`, `UNICODE`;
  compiles a `\p{L}` UTF/UCP pattern, checks capture offsets for a multi-byte
  UTF-8 character, checks a no-match result and a rejected invalid pattern.
* `consumer_posix.c` – POSIX `regcomp`/`regexec` match and no-match.
* `pcre2grep` – version probe, exact line-set comparison for a fixed input
  file, and an exit-code-1 no-match negative check.

Consumers are built outside the source tree against the newly installed
static archives and an identity assertion rejects any library whose reported
version differs from the source tree.

## Honest limitations

* Only the 8-bit library is produced; 16-bit/32-bit and JIT are out of the
  frozen CORE scope, so `pcre2_jit_test` is neither built nor claimed.
* Libraries are static (PCRE2 CMake defaults); no shared objects or SONAME
  are produced.
* CTest reports test-level counts. PCRE2's RunTest does not emit a stable
  per-case total, so no per-case figure is invented; the raw RunTest/pcre2test
  output is preserved verbatim in `logs/`.
* Optional pcre2grep compression support (zlib/bzip2), readline/libedit and
  the `--enable-rebuild-chartables` scenario are not enabled.
* Consumers exercise matching and error handling only; no performance or
  memory-safety tooling is run.
