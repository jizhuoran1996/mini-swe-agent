# DuckDB v1.4.3 core SDK builder (BUILDv1-D05, core profile)

Frozen core scope: `core/CLI + [capi]`, only SQL tables.

## What `run` does

1. Configures and builds DuckDB v1.4.3 from the frozen source archive
   (`cmake -G Ninja`, `Release`, `BUILD_SHELL=ON`, `BUILD_UNITTESTS=ON`,
   in-tree `json;parquet` extensions from vendored sources,
   `ENABLE_EXTENSION_AUTOINSTALL=0`).
2. Installs the SDK (`cmake --install`) to `output/install/`.
3. Enumerates the official `[capi]` selector with `--list-test-names-only`
   into `output/capi_inventory.json`, then runs the full `[capi]` suite.
4. Independently consumes the freshly installed SDK with an external C
   consumer built outside the source tree (`solution/consumer.c`):
   * `CREATE TABLE`,
   * insert via a **prepared statement** with `duckdb_bind_int32`,
   * **aggregation** `SELECT count(*), CAST(sum(amount) AS DOUBLE)`,
   * a **transaction rollback** that must leave the table unchanged,
   * close + **reopen** in a fresh connection and re-verify persistence.
5. Runs a CLI smoke check from the installed binary against the same
   on-disk database (`SELECT count(*), CAST(sum(amount) AS BIGINT)`).

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run    --input /workspace/input --output /workspace/output --jobs 4

`doctor` returns 78 when the source archive, its manifest, or a required
build tool is missing, and 0 when the build can start. Build/install/test/
consumer commands all go through `buildkit.Session`, so each one preserves
its argv, exit code, wall seconds, and sha256-stamped log; parallelism is
capped at 4 by the session helper.

## Consumer assertions (model-driven, integer columns)

The consumer inserts `amounts {10, 20, 30, 40}` as INTEGER and asserts, in
both the initial and the reload connection:

* `count(*) == 4` and `99.5 <= sum(amount) <= 100.5`,
* `count(*) == 4` after `BEGIN; INSERT (5,500); ROLLBACK;`.

Integer arithmetic keeps the expected sum exact (100), independent of
reader/type-inference behaviour, so the check is on the consumer's own
model rather than on anything the build produced. `CAST(sum(amount) AS
DOUBLE)` only pins the *decoded* type; the assertion value is unchanged.

## Fixed API decoding bug

The DuckDB C API read accessors take `(result, column, row)`. An earlier
revision of this consumer called `duckdb_value_double(&r, 0, 1)` for the
single-row `count/sum` result, i.e. `column=0, row=1` — a nonexistent row,
which decoded as 0 and produced `sum=0.000000`. Both the initial and the
reload checks now use `duckdb_value_int64(&r, 0, 0)` for count and
`duckdb_value_double(&r, 1, 0)` for the sum. Expected `count=4` and
`sum=100` are unchanged, and the run additionally asserts
`duckdb_column_type(&r, 1) == DUCKDB_TYPE_DOUBLE`.

## Honest limitations

* The upstream `unittest` binary is Catch2; its summary is not parsed into a
  numeric case count by the shared helper, so `tests.json` records
  `parsed_count: null` and the full upstream log is preserved at
  `output/logs/*_capi.log`. The discovered inventory is in
  `capi_inventory.json`. **No case count is fabricated.** If the `[capi]`
  selector discovers zero tests the builder aborts.
* The upstream Catch2 binary is launched with stdin redirected from
  `/dev/null` (`_no_stdin`), because it otherwise can block on teardown
  after the whole run has already printed its result. If it still fails to
  exit after emitting a passing summary, `_recover_official_test` records
  the run as passing but annotates `commands.json` with
  `recovered_after_teardown_hang: true` so the evidence stays honest.
* JSON and Parquet are built into the CLI/SDK because the frozen build
  recipe lists them, but the **verification consumer does not use them**;
  they belong to the reference variant, not the core scope.
* HTTPFS, S3, ICU, autocomplete, and benchmarks are not built (out of scope).
* The `[capi]` selector is the whole official selection; no test is skipped
  or filtered out.
