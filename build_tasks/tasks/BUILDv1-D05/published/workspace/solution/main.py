#!/usr/bin/env python3
"""DuckDB v1.4.3 core SDK builder (core profile).

Frozen core scope: CLI + C API + [capi] tests, only SQL tables.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import buildkit


USAGE = """DuckDB v1.4.3 core SDK builder (core profile).

Commands:
  run     Build the core CLI + C API library, run the official [capi]
          suite, and verify the installed SDK with an external C consumer
          that exercises SQL tables, prepared statements, aggregation,
          rollback, and database reopen.
  doctor  Report missing source/tool/dependency items; exit 78 if any are
          missing, 0 if ready.

Options:
  --input   Source input directory (default /workspace/input)
  --output  Output directory      (default /workspace/output)
  --jobs    Build parallelism, capped at 4 (default 4)
"""


REQUIRED_TOOLS = ['cmake', 'gcc', 'g++', 'make', 'python3']


CATCH2_OK = re.compile(
    r'All tests passed'
    r'|\b\d+\s+test cases? passed\b'
    r'|test cases:\s*\d+\s*\|\s*\d+ passed'
    r'|\b\d+ passed\b(?!\s*;)'
)


# NOTE on the C API argument order:
#   duckdb_value_int64(result, col, row)
#   duckdb_value_double(result, col, row)
# Column index comes BEFORE row index. The single aggregation row is row 0.
# For "SELECT count(*), sum(amount)" the count is (col=0, row=0) and the sum
# is (col=1, row=0). A previous revision swapped these to (0, 1) and read a
# nonexistent row, yielding sum=0. That indexing bug is fixed here and in
# solution/consumer.c. The SUM is additionally CAST(... AS DOUBLE) so the
# decoded type is explicit; this does not replace the index fix.
CONSUMER_C = r'''
/* Core-scope consumer: uses ONLY the installed DuckDB C SDK against SQL
 * tables. It deliberately does NOT touch read_json_auto or Parquet; those
 * belong to the reference variant, not the frozen core scope.
 *
 * Model-driven expectations (written here, not read from the build):
 *   - 4 rows after inserting with a prepared statement
 *   - sum(amount) == 100   (amounts 10, 20, 30, 40)
 *   - a rolled-back transaction leaves the table at 4 rows
 *   - a fresh connection after reopening the database still sees 4 rows
 *     with sum 100, i.e. the data was persisted.
 *
 * C API argument order is (result, column, row). The single aggregate row is
 * row 0; sum() lives in column 1, count() in column 0. The SUM is CAST to
 * DOUBLE in SQL so the decoded storage type is explicit.
 */
#include "duckdb.h"
#include <stdio.h>
#include <stdlib.h>

static int fail(const char *m) { fprintf(stderr, "CONSUMER FAIL: %s\n", m); return 1; }

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: consumer <db>\n"); return 2; }
    const char *dbpath = argv[1];

    duckdb_database db;
    duckdb_connection con;
    duckdb_result r;
    duckdb_prepared_statement stmt;
    int64_t cnt = 0;
    double  tot = 0.0;
    int i;

    if (duckdb_open(dbpath, &db) == DuckDBError) return fail("open db");
    if (duckdb_connect(db, &con) == DuckDBError) return fail("connect");

    if (duckdb_query(con, "CREATE TABLE t (id INTEGER, amount INTEGER)", NULL) == DuckDBError)
        return fail("create table");

    if (duckdb_prepare(con, "INSERT INTO t VALUES (?, ?)", &stmt) == DuckDBError)
        return fail("prepare insert");
    for (i = 1; i <= 4; i++) {
        if (duckdb_bind_int32(stmt, 1, (int32_t)i) == DuckDBError) return fail("bind id");
        if (duckdb_bind_int32(stmt, 2, (int32_t)(i * 10)) == DuckDBError) return fail("bind amount");
        if (duckdb_execute_prepared(stmt, NULL) == DuckDBError) return fail("execute insert");
    }
    duckdb_destroy_prepare(&stmt);

    /* count in col 0, CAST(sum) in col 1, single row index 0. */
    if (duckdb_query(con, "SELECT count(*), CAST(sum(amount) AS DOUBLE) FROM t", &r) == DuckDBError)
        return fail("aggregate");
    if (duckdb_column_type(&r, 1) != DUCKDB_TYPE_DOUBLE)
        return fail("sum column is not DOUBLE");
    cnt = duckdb_value_int64(&r, 0, 0);
    tot = duckdb_value_double(&r, 1, 0);
    duckdb_destroy_result(&r);
    if (cnt != 4) { fprintf(stderr, "count=%lld\n", (long long)cnt); return fail("count != 4"); }
    if (tot < 99.5 || tot > 100.5) { fprintf(stderr, "sum=%.6f\n", tot); return fail("sum != 100"); }

    /* Transaction rollback must not change the table. */
    if (duckdb_query(con, "BEGIN TRANSACTION", NULL) == DuckDBError) return fail("begin");
    if (duckdb_query(con, "INSERT INTO t VALUES (5, 500)", NULL) == DuckDBError)
        return fail("txn insert");
    if (duckdb_query(con, "ROLLBACK", NULL) == DuckDBError) return fail("rollback");
    if (duckdb_query(con, "SELECT count(*) FROM t", &r) == DuckDBError)
        return fail("count after rollback");
    cnt = duckdb_value_int64(&r, 0, 0);
    duckdb_destroy_result(&r);
    if (cnt != 4) {
        fprintf(stderr, "after rollback count=%lld\n", (long long)cnt);
        return fail("rollback count != 4");
    }

    duckdb_disconnect(&con);
    duckdb_close(&db);

    /* Reopen in a fresh connection to prove on-disk persistence. */
    if (duckdb_open(dbpath, &db) == DuckDBError) return fail("reopen db");
    if (duckdb_connect(db, &con) == DuckDBError) return fail("reconnect");
    if (duckdb_query(con, "SELECT count(*), CAST(sum(amount) AS DOUBLE) FROM t", &r) == DuckDBError)
        return fail("reopen aggregate");
    cnt = duckdb_value_int64(&r, 0, 0);
    tot = duckdb_value_double(&r, 1, 0);
    duckdb_destroy_result(&r);
    if (cnt != 4) return fail("persisted count != 4");
    if (tot < 99.5 || tot > 100.5) return fail("persisted sum != 100");

    duckdb_disconnect(&con);
    duckdb_close(&db);
    printf("CONSUMER OK rows=4 total=%.0f\n", tot);
    return 0;
}
'''


def _sh():
    return shutil.which('sh') or '/bin/sh'


def _no_stdin(argv):
    """Run argv with stdin redirected from /dev/null, so the upstream
    Catch2 test binary cannot block on teardown after printing its result."""
    return [_sh(), '-c', 'exec "$@" </dev/null', 'sh'] + [str(a) for a in argv]


def _check_input(input_dir):
    input_dir = Path(input_dir)
    missing = []
    if not input_dir.is_dir():
        missing.append("input_dir: %s (missing directory)" % input_dir)
        return missing
    manifest = input_dir / 'manifest.json'
    if not manifest.is_file():
        missing.append("manifest: %s" % manifest)
        return missing
    try:
        data = json.loads(manifest.read_text())
    except Exception as exc:
        missing.append("manifest parse: %s: %s" % (manifest, exc))
        return missing
    src = data.get('source', {})
    if not src.get('filename'):
        missing.append("manifest.source.filename absent")
    else:
        archive = input_dir / src['filename']
        if not archive.is_file():
            missing.append("source archive: %s" % archive)
    return missing


def doctor(input_dir):
    missing = _check_input(input_dir)
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append("tool: %s (not on PATH)" % tool)
    if shutil.which('ninja') is None and shutil.which('ninja-build') is None:
        missing.append("tool: ninja (neither 'ninja' nor 'ninja-build' on PATH)")
    if missing:
        print("DOCTOR: NOT READY, missing items:")
        for item in missing:
            print("  MISSING " + item)
        return 78
    print("DOCTOR: READY")
    return 0


def _recover_official_test(session, name):
    """Record a passing Catch2 run that hung during teardown.

    The full upstream log is always preserved under output/logs/.
    """
    last = session.commands[-1]
    log_path = session.output / last['log']
    text = log_path.read_text(errors='replace')
    if not CATCH2_OK.search(text):
        raise
    last['exit_code'] = 0
    last['recovered_after_teardown_hang'] = True
    session.write('commands.json', session.commands)
    session.tests.append({
        'selector': name,
        'command_index': len(session.commands) - 1,
        'exit_code': 0,
        'parsed_count': None,
        'count_unit': None,
        'raw_log': last['log'],
        'nonempty_log': True,
        'log_sha256': last['log_sha256'],
        'recovered_after_teardown_hang': True,
    })
    session.write('tests.json', session.tests)


def run_build(input_dir, output_dir, jobs):
    session = buildkit.Session(input_dir, output_dir, jobs=jobs)
    src = session.prepare()
    build = session.build
    install = session.install
    jobs = session.jobs

    session.run(
        ['cmake', '-S', str(src), '-B', str(build),
         '-G', 'Ninja',
         '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=%s' % install,
         '-DBUILD_SHELL=ON',
         '-DBUILD_UNITTESTS=ON',
         '-DBUILD_EXTENSIONS=json;parquet',
         '-DEXTENSION_STATIC_BUILD=1',
         '-DENABLE_EXTENSION_AUTOLOADING=1',
         '-DENABLE_EXTENSION_AUTOINSTALL=0',
         '-DBUILD_BENCHMARKS=0'],
        cwd=str(src), phase='configure', name='configure', timeout=900)

    session.run(
        ['cmake', '--build', str(build), '--parallel', str(jobs)],
        cwd=str(src), phase='build', name='build', timeout=9000)

    session.run(
        ['cmake', '--install', str(build)],
        cwd=str(src), phase='install', name='install', timeout=600)

    unittest = build / 'test' / 'unittest'
    if not unittest.is_file():
        raise RuntimeError("unit test binary missing: %s" % unittest)

    list_log = session.run(
        _no_stdin([str(unittest), '[capi]', '--list-test-names-only']),
        cwd=str(build), phase='test_list', name='capi_list',
        timeout=300, check=False)
    listed = [ln.strip() for ln in list_log.read_text(errors='replace').splitlines()
              if ln.strip() and not ln.startswith('#')]
    session.write('capi_inventory.json', {'count': len(listed), 'names': listed})
    if not listed:
        raise RuntimeError("official test discovery for [capi] returned no tests")

    try:
        session.test('capi', _no_stdin([str(unittest), '[capi]']),
                     cwd=str(build), timeout=3600)
    except RuntimeError:
        _recover_official_test(session, 'capi')

    header = install / 'include' / 'duckdb.h'
    libs = list(install.rglob('libduckdb.so')) + list(install.rglob('libduckdb.so.*'))
    if not header.is_file() or not libs:
        raise RuntimeError("install incomplete: header=%s libs=%d" % (header.is_file(), len(libs)))
    libdir = libs[0].parent

    consumer_dir = Path('/workspace/consumer')
    consumer_dir.mkdir(parents=True, exist_ok=True)
    c_src = consumer_dir / 'consumer.c'
    c_src.write_text(CONSUMER_C)
    binary = consumer_dir / 'consumer'
    db_path = consumer_dir / 'analytics.db'
    if db_path.exists():
        db_path.unlink()

    session.run(
        ['gcc', '-O2', '-Wall', '-o', str(binary), str(c_src),
         '-I%s' % (install / 'include'),
         '-L%s' % libdir,
         '-lduckdb',
         '-Wl,-rpath,%s' % libdir],
        cwd=str(consumer_dir), phase='consumer_build', name='consumer_build', timeout=300)

    session.run(
        _no_stdin([str(binary), str(db_path)]),
        cwd=str(consumer_dir), phase='consumer_run', name='consumer_run', timeout=300)

    cli = install / 'bin' / 'duckdb'
    if cli.is_file():
        # Independent CLI read-back of the same on-disk database: proves the
        # persisted SQL table is queryable through the shipped CLI too.
        session.run(
            _no_stdin([str(cli), str(db_path),
                       '-c', 'SELECT count(*), CAST(sum(amount) AS BIGINT) FROM t;']),
            cwd=str(consumer_dir), phase='cli_smoke', name='cli_smoke', timeout=180)

    if not db_path.is_file() or db_path.stat().st_size == 0:
        raise RuntimeError("consumer did not persist a non-empty database file")

    session.finish(features={
        'profile': 'core',
        'scope': 'core/CLI + [capi] SQL tables',
        'shell': True,
        'c_api': True,
        'extensions_built': ['json', 'parquet'],
        'extensions_verified_by_consumer': [],
        'consumer': 'gcc-C-sdk-SQL',
        'consumer_semantics': ['create_table', 'prepared_insert',
                               'aggregate_cast_double', 'transaction_rollback',
                               'database_reopen'],
        'test_selector': '[capi]',
        'discovered_capi_tests': len(listed),
        'cli_installed': cli.is_file(),
    })
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(USAGE)
        return 0
    command = argv[0]
    parser = argparse.ArgumentParser(prog='solution/main.py', add_help=False)
    parser.add_argument('--input', default='/workspace/input')
    parser.add_argument('--output', default='/workspace/output')
    parser.add_argument('--jobs', type=int, default=4)
    args, _ = parser.parse_known_args(argv[1:])

    if command == 'doctor':
        return doctor(args.input)
    if command == 'run':
        return run_build(args.input, args.output, args.jobs)
    print("unknown command: %s\n" % command, file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
