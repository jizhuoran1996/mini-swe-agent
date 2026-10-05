# PostgreSQL 17.5 core build + qualification

Builds the pinned PostgreSQL 17.5 source release into a private prefix and
qualifies it with the official core regression suite plus an out-of-tree
libpq consumer.

## Usage

    # Readiness probe (no build): lists exact missing source/tool/dependency items
    python3 solution/main.py doctor --input /workspace/input
    # exit 0 means ready, exit 78 means something is missing

    # Full build + official test + install + consumer verification
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

## What the run does

1. Session.prepare() verifies the archive sha256 and extracts to /workspace/src.
2. /workspace/src/configure --prefix=/workspace/output/install from /workspace/build.
3. make -j4 all, then make install into the private prefix.
4. make check MAX_CONNECTIONS=2 (official core regression entrypoint).
5. initdb a throwaway cluster with freshly installed binaries on a private unix
   socket/port, compile solution/consumer_libpq.c against the newly installed
   libpq, run it, stop, restart the same data directory, and re-verify committed
   versus rolled-back rows through the installed psql.

All build/configure/install/test/consumer commands go through the trusted
buildkit.Session.run / .test helpers, so exit codes and complete logs are
preserved under output/logs/ and summarized in output/commands.json and
output/tests.json.

## Artifacts

* output/install - server, client tools, libpq, and headers
* output/install.tar.gz and output/install_manifest.json
* output/commands.json, output/tests.json, output/coverage.json
* output/consumer_evidence.json - libpq linkage plus post-restart row counts
* output/run.json - final session summary

## Honest limitations

* Frozen core profile only: default server/clients/libpq; no SSL/LZ4/Zstandard,
  no LLVM JIT, no contrib, no isolation suite, no check-world.
* pg_regress does not emit any of the summary formats recognised by the helper
  test parser, so parsed_count is legitimately null; the real count is extracted
  from the preserved upstream log in coverage.json instead of being invented.
* The build relies on whatever headers the base image provides; doctor reports
  their presence but the core profile does not require them.
* Only locally reachable unix-socket operation is exercised; no external
  authentication, TLS, or clustered deployment is validated.
