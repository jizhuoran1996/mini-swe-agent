# BUILDv1-B05 — Node.js CORE source build (small-icu)

Builds the frozen Node.js `v22.16.0` source archive with a fixed, fully local
internationalization configuration, runs the official stream and message test
sub-systems, installs the runtime, and verifies it from a consumer that lives
outside the source tree.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input          # exit 78 if not ready, 0 if ready
    python3 solution/main.py run --input input --output output --jobs 4

`--help` never triggers a build. `doctor` verifies the input directory, the
frozen manifest, the sha256 of the source archive, a couple of mandatory
archive entries and the presence of `gcc`, `g++`, `make`, `python3` and `tar`.

## What CORE (this profile) builds

* `--with-intl=small-icu` — ICU is compiled from the in-tree `deps/icu-small`,
  no network and no external ICU source are used.
* `--v8-disable-temporal-support` is passed when the frozen revision's
  `configure.py` advertises it; the actual decision is recorded in
  `output/features.json`.
* Build parallelism is capped at 4 and the official test runner uses at most 2
  workers.

## Evidence written to `--output`

* `features.json` — frozen configure/intl/temporal inventory
* `test_inventory.json` — exact official test selection captured *before* run
* `commands.json`, `logs/*.log` — every build/test/consumer command with exit code and log hash
* `tests.json` — official test selectors, raw logs and any parser-derived counts
* `node-runtime.tar.gz`, `install.tar.gz`, `install_manifest.json` — the installed runtime
* `run.json` — summary written by the trusted helper

The consumer (`output`-adjacent `/workspace/consumer`) runs
`bin/node check_runtime.js` (execPath, `process.versions`, ICU presence, Intl
en-US formatting, streams, worker_threads, child_process) and then
`bin/node server.js` serving on a dynamic loopback port that is exercised by an
independent Python client over a raw socket before the server is shut down.

## Honest limitations

* CORE uses **small-icu**, so only English locale data is compiled in. The
  consumer records `Intl.DateTimeFormat('de-DE').resolvedOptions().locale` and
  asserts only that it resolves without throwing; non-English formatting from
  the reference profile is *not* claimed here.
* Temporal remains explicitly disabled in CORE; no Rust/Cargo vendor tree is
  required or consumed.
* Official test pass counts come from `tools/test.py`'s own output. Where the
  helper's parser cannot derive a numeric count, `tests.json` stores a null
  count with the raw upstream log preserved — counts are never fabricated.
* The reported coverage is limited to the frozen selectors (`test-stream-*`
  and `test/message`) on Linux x86_64; it does not represent the full upstream
  CI matrix.
* Sub-second determinism and byte-identical rebuilds are out of scope.
