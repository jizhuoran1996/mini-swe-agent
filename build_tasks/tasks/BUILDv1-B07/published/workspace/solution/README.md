# BUILDv1-B07 (core profile) - source-built PHP CLI

`solution/main.py` source-builds PHP 8.4.8 from the frozen php-src archive that
the harness mounts at `/workspace/input`, installs a CLI interpreter, runs the
official PHPT suites for `tests/lang` and `ext/json/tests`, and consumes the
installed runtime from outside the source tree.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input
    python3 solution/main.py run --input input --output output --jobs 4

`--help` never performs a build. `doctor --input input` prints the exact missing
source archive / build tool / library-dependency items and exits `78` when any
is missing, `0` when the environment is ready.

## Build pipeline (all steps via the trusted `buildkit.Session`)

1. `Session.prepare()` verifies `source.tar.gz` against the manifest sha256 and
extracts it safely into `/workspace/src` (top-level archive dir stripped).
2. Official test inventory (`tests_inventory.json`) is captured before any test
runs.
3. `./buildconf --force`, then
`./configure --prefix=<install> --with-pdo-sqlite --with-sqlite3 --without-pear`.
4. `make -j<BUILD_JOBS>` (capped at 4) and `make test` on `tests/lang` and
`ext/json/tests` separately with `TEST_PHP_ARGS=-j<2>` and
`NO_INTERACTION=1` / `REPORT_EXIT_STATUS=0` so the real PHPT summary is
preserved in the log even when individual cases fail.
5. `make install` into the session install prefix; the interpreter is never
taken from the host or from the source tree.
6. Out-of-tree consumer validation using only `install/bin/php`: `-n` (`-v`,
`--ri json`, `--ri pdo_sqlite`, `-r` module assertions, a language/JSON self
test) plus a two-process SQLite round trip (`produce.php` writes JSON payloads
into a fresh database, `verify.php` reopens it in a *new* process and asserts
the decoded data).

## Outputs

- `install/` and `install.tar.gz` / `php-install.tar.gz`
- `install_manifest.json`, `commands.json`, `tests.json`, `run.json`
- `logs/` with the full stdout/stderr of every command
- `tests_inventory.json` (pre-run discovery) and `phpt_coverage.json`
(PASS/FAIL/SKIP/WARN/XFAIL/BORKED counts parsed from the upstream summary)
- consumer PHP fixtures written under `/workspace/consumer`

## Honest limitations

- The core scope is the default PHP build plus CLI; PHPT coverage is limited to
`tests/lang` and `ext/json/tests`. `ext/standard/tests/array`,
`ext/pdo_sqlite/tests` and the reference SQLite contract are *not* exercised
here even though SQLite support is compiled in and consumed functionally.
- PHPT counts are parsed from the upstream `TEST RESULT SUMMARY` block. When a
label is absent the value stays `null`; no case counts are invented.
- A missing toolchain, libxml2 or sqlite3 development package, or a corrupt
source archive fails honestly (`doctor` exits 78, `run` aborts) rather than
being skipped.
- Only Linux x86_64 behaviour covered by the frozen test set is claimed; this
is not upstream cross-platform CI.
- No network access is used at any point.
