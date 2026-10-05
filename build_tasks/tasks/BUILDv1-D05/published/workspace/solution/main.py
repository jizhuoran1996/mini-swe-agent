#!/usr/bin/env python3
"""DuckDB v1.4.3 core SDK build (core profile): CLI + C API + json/parquet.

Usage:
  python3 solution/main.py --help
  python3 solution/main.py doctor  --input /workspace/input
  python3 solution/main.py run     --input /workspace/input --output /workspace/output --jobs 4
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import buildkit


USAGE = """DuckDB v1.4.3 core SDK builder (core profile).

Commands:
  run     Build the CLI, C API, and json/parquet extensions; run [capi]
          official tests; build and execute an external C consumer.
  doctor  Report exact missing source/tool/dependency items; exit 78 if any
          are missing, 0 if ready.

Options:
  --input   Source input directory (default /workspace/input)
  --output  Output directory      (default /workspace/output)
  --jobs    Build parallelism, capped at 4 (default 4)
"""


REQUIRED_TOOLS = ['cmake', 'ninja', 'gcc', 'g++', 'make', 'python3']


CONSUMER_C = r'''
#include "duckdb.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int fail(const char *m) { fprintf(stderr, "CONSUMER FAIL: %s\n", m); return 1; }

int main(int argc, char **argv) {
    if (argc < 4) { fprintf(stderr, "usage: consumer <db> <json> <parquet>\n"); return 2; }
    const char *dbpath   = argv[1];
    const char *jsonpath = argv[2];
    const char *parqpath = argv[3];

    duckdb_database db;
    duckdb_connection con;
    duckdb_result r;

    if (duckdb_open(dbpath, &db) == DuckDBError) return fail("open db");
    if (duckdb_connect(db, &con) == DuckDBError) return fail("connect");

    char sql[4096];

    snprintf(sql, sizeof sql,
        "CREATE TABLE sales AS SELECT * FROM read_json_auto('%s')", jsonpath);
    if (duckdb_query(con, sql, NULL) == DuckDBError) return fail("create from json");

    if (duckdb_query(con, "SELECT count(*), sum(amount) FROM sales", &r) == DuckDBError)
        return fail("aggregate");
    int64_t cnt = duckdb_value_int64(&r, 0, 0);
    double  tot = duckdb_value_double(&r, 0, 1);
    duckdb_destroy_result(&r);
    if (cnt != 4)  return fail("json row count != 4");
    if (tot < 27.0 || tot > 29.0) return fail("json sum out of range");

    snprintf(sql, sizeof sql,
        "COPY (SELECT id, name, amount FROM sales ORDER BY id) TO '%s' (FORMAT PARQUET)",
        parqpath);
    if (duckdb_query(con, sql, NULL) == DuckDBError) return fail("export parquet");

    duckdb_disconnect(&con);
    duckdb_close(&db);

    if (duckdb_open(dbpath, &db) == DuckDBError) return fail("reopen db");
    if (duckdb_connect(db, &con) == DuckDBError) return fail("reconnect");

    if (duckdb_query(con, "SELECT count(*) FROM sales", &r) == DuckDBError)
        return fail("persist count");
    cnt = duckdb_value_int64(&r, 0, 0);
    duckdb_destroy_result(&r);
    if (cnt != 4) return fail("persisted row count != 4");

    snprintf(sql, sizeof sql, "SELECT count(*) FROM '%s'", parqpath);
    if (duckdb_query(con, sql, &r) == DuckDBError) return fail("reread parquet");
    cnt = duckdb_value_int64(&r, 0, 0);
    duckdb_destroy_result(&r);
    if (cnt != 4) return fail("parquet row count != 4");

    duckdb_disconnect(&con);
    duckdb_close(&db);
    printf("CONSUMER OK rows=4 total=%.2f\n", tot);
    return 0;
}
'''


JSON_SAMPLE = [
    {"id": 1, "name": "alpha", "amount": 5.5},
    {"id": 2, "name": "beta",  "amount": 6.5},
    {"id": 3, "name": "gamma", "amount": 7.5},
    {"id": 4, "name": "delta", "amount": 8.0},
]


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
    archive = input_dir / src.get('filename', '')
    if not src.get('filename'):
        missing.append("manifest.source.filename absent")
    elif not archive.is_file():
        missing.append("source archive: %s" % archive)
    return missing


def doctor(input_dir):
    missing = _check_input(input_dir)
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append("tool: %s (not on PATH)" % tool)
    if shutil.which('ninja') is None and shutil.which('ninja-build') is None:
        missing.append("tool: ninja-build (both 'ninja' and 'ninja-build' absent)")
    if missing:
        print("DOCTOR: NOT READY, missing items:")
        for item in missing:
            print("  MISSING " + item)
        return 78
    print("DOCTOR: READY")
    return 0


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
        [str(unittest), '[capi]', '--list-test-names-only'],
        cwd=str(build), phase='test_list', name='capi_list', timeout=300)
    listed = [ln.strip() for ln in list_log.read_text(errors='replace').splitlines() if ln.strip()]
    if not listed:
        raise RuntimeError("official test discovery for [capi] returned no tests")

    session.test('capi', [str(unittest), '[capi]'],
                 cwd=str(build), timeout=2400)

    header = install / 'include' / 'duckdb.h'
    libs = list(install.rglob('libduckdb.so')) + list(install.rglob('libduckdb.so.*'))
    if not header.is_file() or not libs:
        raise RuntimeError("install incomplete: header=%s libs=%d" % (header.is_file(), len(libs)))
    libdir = libs[0].parent

    consumer_dir = Path('/workspace/consumer')
    consumer_dir.mkdir(parents=True, exist_ok=True)
    c_src = consumer_dir / 'consumer.c'
    c_src.write_text(CONSUMER_C)
    json_path = consumer_dir / 'input.json'
    json_path.write_text(json.dumps(JSON_SAMPLE))
    binary = consumer_dir / 'consumer'
    db_path = consumer_dir / 'analytics.db'
    parq_path = consumer_dir / 'sales.parquet'

    session.run(
        ['gcc', '-O2', '-Wall', '-o', str(binary), str(c_src),
         '-I%s' % (install / 'include'),
         '-L%s' % libdir,
         '-lduckdb',
         '-Wl,-rpath,%s' % libdir],
        cwd=str(consumer_dir), phase='consumer_build', name='consumer_build', timeout=300)

    session.run(
        [str(binary), str(db_path), str(json_path), str(parq_path)],
        cwd=str(consumer_dir), phase='consumer_run', name='consumer_run', timeout=300)

    if not parq_path.is_file() or parq_path.stat().st_size == 0:
        raise RuntimeError("consumer did not produce a non-empty parquet file")

    session.finish(features={
        'profile': 'core',
        'shell': True,
        'c_api': True,
        'extensions': ['json', 'parquet'],
        'cli_installed': any(install.rglob('duckdb')),
        'test_selector': '[capi]',
        'consumer': 'gcc-C-sdk',
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
