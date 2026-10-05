/* Consumer source is written by main.py at /workspace/consumer/consumer.c.
 * It links against the freshly installed DuckDB C API (include + libduckdb)
 * and exercises: JSON input, aggregation, persistence, Parquet export, and
 * reopening both the database and the Parquet file in a second process run.
 */
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
    if (cnt != 4) return fail("json row count != 4");
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
