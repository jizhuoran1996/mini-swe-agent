# BUILDv1-B05 — Node.js CORE source build (small-icu)

Builds the frozen Node.js `v22.16.0` source archive with a fixed, fully local
internationalization configuration, runs the official stream and message test
sub-systems using the freshly installed binary, installs the runtime and
verifies it from a consumer located outside the source tree.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input          # exit 78 if not ready, 0 if ready
    python3 solution/main.py run --input input --output output --jobs 4

`--help` never triggers a build. `doctor` verifies the input directory, the
frozen manifest, the sha256 of the source archive, a couple of mandatory
archive entries (`configure.py`, `deps`, `tools`) and the presence of `gcc`,
`g++`, `make`, `python3` and `tar`.

## What CORE (this profile) builds

* `--with-intl=small-icu` — ICU is compiled from the in-tree `deps/icu-small`,
  no network and no external ICU source are used.
* `--v8-disable-temporal-support` is passed when the frozen revision's
  `configure.py` advertises it; the actual decision is recorded in
  `output/features.json`.
* Build parallelism is capped at 4; the official `tools/test.py` runner is
  driven with the short form `-j 2` (its only parallel flag — `--jobs` is not a
  recognised option) and forced to use the newly installed runtime via the
  supported `--shell <install>/bin/node` option.

## Official test discovery & selectors

Node's `tools/test.py` takes selectors that are **relative to the test ROOT
(`test/`) without the leading `test/` and without the `.js` suffix**, i.e.
`parallel/test-stream-legacy`. The build discovers every
`test/parallel/test-stream-*.js` (the frozen 32-test stream set) plus every
`test/message/*.js`, converts each file path to that selector form, snapshots
the exact inventory to `output/test_inventory.json` **before running anything**,
and then executes:

    python3 tools/test.py -j 2 --shell <install>/bin/node <selectors...>

The installed runtime is used for the tests; the preloaded bootstrap `node`
from `/opt/bootstrap` is never consulted by the runner or by the consumer.

## Evidence written to `--output`

* `features.json` — frozen configure/intl/temporal inventory
* `test_inventory.json` — exact official test selection captured *before* run
* `commands.json`, `logs/*.log` — every build/test/consumer command with exit code and log hash
* `tests.json` — official test selectors, raw logs and any parser-derived counts
* `node-runtime.tar.gz`, `install.tar.gz`, `install_manifest.json` — the installed runtime
* `run.json` — summary written by the trusted helper

## Consumer

The consumer lives under `/workspace/consumer`, outside the source tree, and
drives the installed `bin/node`:

* `check_runtime.js` asserts `process.execPath`, `process.versions.node`, the
  presence of ICU (`process.versions.icu`), en-US `Intl.NumberFormat`, a
  `stream` transform, `worker_threads` and a forked `child_process`. It
  *records* (but does not assert on) the `process.config.variables` flags such
  as `node_use_icu`, whose names/values differ between revisions and intl
  modes; the portable, real indicator of a compiled-in ICU is
  `process.versions.icu`.
* `server.js` binds a dynamic loopback port; an independent Python socket
  client fetches it and confirms the response before the server is cleanly shut
  down (stdin EOF).

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
