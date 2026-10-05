/* Core-scope consumer: uses ONLY the installed DuckDB C SDK against SQL
 * tables. Deliberately does NOT touch read_json_auto or Parquet; those
 * belong to the reference variant, not the frozen core scope.
 *
 * Model-driven expectations (written here, not read from the build):
 *   - 4 rows after inserting via a prepared statement
 *   - sum(amount) == 100   (amounts 10, 20, 30, 40)
 *   - a rolled-back transaction leaves the table at 4 rows
 *   - a fresh connection after reopening the database still sees 4 rows
 *     with sum 100, proving on-disk persistence.
 *
 * main.py writes this file verbatim to /workspace/consumer/consumer.c.
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

    if (duckdb_query(con, "SELECT count(*), sum(amount) FROM t", &r) == DuckDBError)
        return fail("aggregate");
    cnt = duckdb_value_int64(&r, 0, 0);
    tot = duckdb_value_double(&r, 0, 1);
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
    if (duckdb_query(con, "SELECT count(*), sum(amount) FROM t", &r) == DuckDBError)
        return fail("reopen aggregate");
    cnt = duckdb_value_int64(&r, 0, 0);
    tot = duckdb_value_double(&r, 0, 1);
    duckdb_destroy_result(&r);
    if (cnt != 4) return fail("persisted count != 4");
    if (tot < 99.5 || tot > 100.5) return fail("persisted sum != 100");

    duckdb_disconnect(&con);
    duckdb_close(&db);
    printf("CONSUMER OK rows=4 total=%.0f\n", tot);
    return 0;
}
