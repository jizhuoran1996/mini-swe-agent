# DuckDB v1.4.3 core SDK builder (BUILDv1-D05, core profile)

Builds the DuckDB CLI and C API from the frozen source archive, links the
in-tree `json` and `parquet` extensions statically, runs the official `[capi]`
unit test selector, and verifies the freshly installed SDK with an external C
consumer that imports JSON, aggregates, persists a database, exports Parquet,
and re-reads both the database and the Parquet file.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run    --input /workspace/input --output /workspace/output --jobs 4

`doctor` returns 78 if the source archive, its manifest, or any required build
tool is missing, and 0 when everything needed to launch the build is present.

## What `run` produces

* `output/install/` - installed SDK (headers, `libduckdb`, CLI, statically
  linked json/parquet extensions).
* `output/logs/` - one log per subprocess, with argv, cwd, exit code, wall
  seconds, and sha256.
* `output/commands.json`, `output/tests.json`, `output/install_manifest.json`,
  `output/run.json`, `output/install.tar.gz`.
* `/workspace/consumer/` - the C consumer source, its database, and the
  exported Parquet file.

All build / install / test / consumer commands go through `buildkit.Session`
so exit codes and logs are preserved. `BUILD_JOBS` is capped at 4 by the
session helper.

## Honest limitations

* The official `[capi]` runner is a Catch2 binary; its summary is not parsed
  into a numeric case count by the shared helper, so `tests.json` records
  `parsed_count: null` and the full upstream log is preserved at
  `output/logs/*_capi.log`. This is intentional: no case count is fabricated.
* Extensions are built statically (`EXTENSION_STATIC_BUILD=1`) so the
  consumer does not depend on external signature-signed loadable extension
  files. Runtime auto-loading is enabled but auto-install and network are not.
* Only the core profile is targeted: CLI + `[capi]` + SQL tables. HTTPFS, S3,
  ICU, autocomplete, and benchmarks are out of scope and are not built.
* The `[capi]` selector is the whole official selection; if upstream v1.4.3
  accidentally contained zero such tests the builder aborts instead of
  claiming success.
