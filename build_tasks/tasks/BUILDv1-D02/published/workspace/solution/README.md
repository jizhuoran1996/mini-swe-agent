# BUILDv1-D02 — MariaDB source build & qualification (core profile)

Builds `MariaDB` 11.4.5 (commit `0771110266ff5c04216af4bf1243c65f8c67ccf4`) from the
source archive and qualifies the freshly installed server with the official
upstream tests plus an independent local-transaction consumer.

## Usage

```
# Readiness probe (no build, no extraction):
python3 solution/main.py doctor --input input
#  exit 0  -> source archive, toolchain and required submodule stubs present
#  exit 78 -> prints the exact missing source-file/tool/submodule items

# Full source build + official tests + install + consumer:
python3 solution/main.py run --input input --output output --jobs 4
```

`--help` works without any build (`python3 solution/main.py --help`).

## Pipeline (all steps go through `buildkit.Session`)

1. `prepare()` — verify the archive SHA-256 and safely extract to `/workspace/src`.
2. `cmake -G Ninja` configure — `RelWithDebInfo`, `WITH_UNIT_TESTS=ON`,
   `WITH_SSL=system`, plan-incompatible storage engines disabled.
3. `cmake --build --parallel <jobs>` (capped at 4).
4. CTest unit tests (`ctest --output-on-failure -j 2`).
5. `mysql-test/mysql-test-run.pl --parallel=2 main.insert main.select`.
6. `cmake --install` into `<output>/install`.
7. Consumer verification out of tree: initialize *two* private datadirs, start
   the server on a Unix socket in a session-managed child process, run a
   transaction (COMMIT / ROLLBACK), assert an aggregate, `SHOW ENGINES`, take a
   `mariadb-dump` backup, restore into the second datadir and re-verify.

Evidence: `<output>/commands.json` (argv, exit code, wall time, log digest),
`<output>/tests.json` (parsed upstream counts only when the upstream log really
contains them), `<output>/install_manifest.json`, `<output>/install.tar.gz` and
`<output>/run.json`.

## Honest limitations

- The upstream codeload archive is a git snapshot: the `libmariadb` (Connector/C)
  and `extra/wolfssl` submodules are usually *not* populated. `doctor` reports
  the missing `libmariadb/CMakeLists.txt` explicitly and exits 78 rather than
  silently disabling required features. Once the submodule trees are staged
  under `/workspace/input` (or extracted alongside the source), the build and
  the official tests run unchanged.
- `TEST_JOBS` is capped at 2 and `BUILD_JOBS` at 4; MTR gets its own private
  `--vardir` under the build tree so it never touches another server's datadir.
- `mysql-test-run.pl --mem` is deliberately omitted (matches the reference).
- No network access, no `sudo`, no host mutation; every subprocess is invoked
  with an explicit argv list.
- Peak resource figures (compile wall time, RSS) are measured by the harness,
  not asserted here.
