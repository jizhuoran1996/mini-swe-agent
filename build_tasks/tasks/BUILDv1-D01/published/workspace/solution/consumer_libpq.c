/* Out-of-tree libpq consumer: drives committed and rolled-back transactions
 * against the freshly installed PostgreSQL server. Exits non-zero unless the
 * transactional invariants hold. */
#include <stdio.h>
#include <stdlib.h>
#include <libpq-fe.h>

static void bail(PGconn *c, const char *what) {
    fputs("FAIL: ", stderr);
    fputs(what, stderr);
    fputs(": ", stderr);
    if (c) fputs(PQerrorMessage(c), stderr);
    fputc(10, stderr);
    if (c) PQfinish(c);
    exit(1);
}

static PGresult *qok(PGconn *c, const char *sql) {
    PGresult *r = PQexec(c, sql);
    ExecStatusType s = PQresultStatus(r);
    if (s != PGRES_COMMAND_OK && s != PGRES_TUPLES_OK) {
        fputs("FAIL sql: ", stderr);
        fputs(sql, stderr);
        fputs(": ", stderr);
        fputs(PQerrorMessage(c), stderr);
        fputc(10, stderr);
        PQclear(r);
        PQfinish(c);
        exit(1);
    }
    return r;
}

int main(int argc, char **argv) {
    int i;
    long total, committed, rolled;
    PGresult *r;
    char q[128];
    PGconn *c;
    if (argc < 2) {
        fputs("usage: consumer_libpq <conninfo>", stderr);
        fputc(10, stderr);
        return 2;
    }
    c = PQconnectdb(argv[1]);
    if (PQstatus(c) != CONNECTION_OK) bail(c, "connect");
    printf("LIBPQ_VERSION=%d", PQlibVersion());
    fputc(10, stdout);

    PQclear(qok(c, "DROP TABLE IF EXISTS tx_demo"));
    PQclear(qok(c, "CREATE TABLE tx_demo(id integer PRIMARY KEY, note text NOT NULL)"));
    PQclear(qok(c, "BEGIN"));
    for (i = 0; i < 1000; i++) {
        snprintf(q, sizeof(q), "INSERT INTO tx_demo VALUES (%d,'committed')", i);
        PQclear(qok(c, q));
    }
    PQclear(qok(c, "COMMIT"));

    PQclear(qok(c, "BEGIN"));
    for (i = 0; i < 50; i++) {
        snprintf(q, sizeof(q), "INSERT INTO tx_demo VALUES (%d,'rolledback')", 100000 + i);
        PQclear(qok(c, q));
    }
    PQclear(qok(c, "ROLLBACK"));

    PQclear(qok(c, "INSERT INTO tx_demo VALUES (200000,'post-rollback')"));

    r = qok(c, "SELECT count(*) FROM tx_demo");
    total = strtol(PQgetvalue(r, 0, 0), NULL, 10);
    PQclear(r);
    r = qok(c, "SELECT count(*) FROM tx_demo WHERE note='committed'");
    committed = strtol(PQgetvalue(r, 0, 0), NULL, 10);
    PQclear(r);
    r = qok(c, "SELECT count(*) FROM tx_demo WHERE note='rolledback'");
    rolled = strtol(PQgetvalue(r, 0, 0), NULL, 10);
    PQclear(r);

    printf("RESULT total=%ld committed=%ld rolledback=%ld", total, committed, rolled);
    fputc(10, stdout);
    PQfinish(c);

    if (total != 1001 || committed != 1000 || rolled != 0) {
        fputs("FAIL transactional invariants violated", stderr);
        fputc(10, stderr);
        return 1;
    }
    puts("CONSUMER_OK");
    return 0;
}
