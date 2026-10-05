# BUILDv1-D02 — MariaDB source build & qualification (core profile)

Builds and qualifies **MariaDB 11.4.5** (commit `0771110266ff5c04216af4bf1243c65f8c67ccf4`)
from the locked source archive, using the official CTest unit selection plus
the official `main.insert` / `main.select` regression files, then installs the
result into a private prefix and exercises it from outside the source tree.

## Usage

```
python3 solution/main.py --help                                  # no build needed
python3 solution/main.py doctor --input input                    # readiness probe
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` exits `0` when the archive, toolchain and offline dependencies are
usable and `78` otherwise, printing the exact missing `source:` / `source-file:` /
`tool:` / `dependency:` items. `run` performs the same probe first and returns
`78` instead of starting a build that cannot succeed.

## Pipeline (every step goes through `buildkit.Session`)

1. `prepare()` — SHA-256 check of the archive, safe extraction into `/workspace/src`.
2. `cmake -G Ninja` configure: `RelWithDebInfo`, `WITH_UNIT_TESTS=ON`,
   `WITH_SSL=system`, `WITH_LIBFMT=system` (system libfmt detected by the driver),
   plan-incompatible engines (ColumnStore/RocksDB/TokuDB/Mroonga/Spider/Connect/OQGraph)
   and wsrep/S3 turned off.
3. `cmake --build --parallel <jobs>` (capped at 4).
4. Official CTest unit selection (`ctest --output-on-failure -j 2`).
5. Official MTR regression run `--parallel=2 main.insert main.select`, using the
   runner discovered in the build tree (`build/mysql-test/mariadb-test-run.pl`)
   or, failing that, the source tree, with its own private `--vardir`.
6. `cmake --install` into `<output>/install`.
7. Consumer verification outside the source tree: two private datadirs
   (`mariadb-install-db`), two private `mariadbd` processes on Unix sockets
   (`--skip-networking`, dedicated pid/socket/error-log, `--no-defaults`),
   a transaction with a committed and a rolled-back row, an aggregate assertion
   `3 / 6 / 30.50`, `SHOW ENGINES` must list InnoDB and Aria, `mariadb-dump`
   export, restore into the second datadir and re-verification of the aggregate.

## Installed layout (STANDALONE)

MariaDB's `cmake/install_layout.cmake` for the default `INSTALL_LAYOUT=STANDALONE`
gives `INSTALL_BINDIR=bin`, `INSTALL_SBINDIR=bin`, `INSTALL_SCRIPTDIR=scripts`
and `INSTALL_SHAREDIR=share/mariadb`.  Consequences for the consumer:

- `mariadbd`, `mariadb`, `mariadb-dump` end up in `<prefix>/bin/`.
- `mariadb-install-db` (and the `mysql_install_db` alias) end up in
  `<prefix>/scripts/`, **not** `<prefix>/bin/`.

The driver resolves each helper from the actual installed tree instead of
assuming `bin/`: it tries `scripts/` first, then `bin/`, then `share/*`, then a
recursive search for known leaf names (`mariadb-install-db`,
`mysql_install_db`, their `.pl` forms, `mariadb-dump`, `mysqldump`).  Helpers
are executed with `perl` when the resolved file is a `*.pl` script, directly
when the executable bit is set, and via `sh` otherwise — never with an
interpreter mismatch that would silently skip the initialize step.

## Evidence

`<output>/commands.json` (argv, cwd, exit code, wall time, log digest),
`<output>/tests.json` (parsed upstream counts only when the upstream log really
contains a summary — never synthesised), `<output>/logs/*`,
`<output>/install_manifest.json`, `<output>/install.tar.gz`, `<output>/run.json`.

## Harness naming

MariaDB 11.4.x ships its official runner as `mysql-test/mariadb-test-run.pl`;
`mysql-test/lib/v1/mysql-test-run.pl` is an obsolete alternate that upstream no
longer installs at the top of `mysql-test/`. `doctor` accepts either name and
`run` resolves the runner at execution time, preferring the build tree.

## Honest limitations

- This is an **offline** build. The upstream build downloads bundled `fmt`
  through an `ExternalProject` when no system copy is used, which cannot work
  without network access. `doctor` therefore requires a system libfmt
  (pkg-config `fmt` or `fmt/format.h`) and reports
  `dependency:libfmt ...`, exiting `78`, if it is genuinely absent; if an fmt
  source tree/archive is provided next to the source (`fmt-*` under the input
  directory, `/workspace/cache`, `/opt` or `/usr/local/src`) it is staged so
  the bundled build skips the download step.
- `WITH_AWS_SDK=OFF`, `WITH_S3=OFF` and `PLUGIN_S3=NO` are passed because the S3
  storage engine pulls the AWS SDK in from the network; this does not affect the
  transactional engines or any selected test.
- `TEST_JOBS` is 2 and `BUILD_JOBS` is capped at 4. MTR gets a private
  `--vardir` under the build tree, so it can never attach to another server.
- `mariadb-test-run.pl --mem` is deliberately not used.
- The private consumer servers are child processes of the driver (they have no
  meaningful exit code to record while running); every SQL/tool invocation they
  serve goes through `Session.run` and is logged.
- `WITH_AWS_SDK`, `WITH_S3` and `PLUGIN_S3` are harmless no-ops on trees that do
  not define them.
