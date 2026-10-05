# BUILDv1-E08 — Babel toolchain build + installed consumer verification

Builds the Babel monorepo (release ref `v7.27.1`, commit
`eebd3a06021c13d335b5b0bd79734df3abbea678`) from the frozen `source.tar.gz`, runs the
core-profile official suites (`babel-core`, `babel-parser`), packs every workspace
package into local tarballs, and consumes the full `@babel/*` closure from an
independent project outside the source tree.

## Usage

```
python3 solution/main.py doctor --input /workspace/input       # exit 78 if not ready, 0 if ready
python3 solution/main.py run    --input /workspace/input --output /workspace/output --jobs 4
```

`--help` prints usage with no build. `--jobs` is capped at 4 by `Session`; official
tests run with `TEST_JOBS=2`.

## Toolchain contract

The runtime supplies pinned Corepack / Yarn 4.9.1 plus a hydrated dependency cache at
`/workspace/cache/yarn`. All yarn calls use Yarn-4 semantics only:

* `yarn install --immutable`
* `YARN_ENABLE_NETWORK=0`, `YARN_ENABLE_GLOBAL_CACHE=false`, `YARN_CACHE_FOLDER=<cache>`

No Yarn-1 flags are used. When `yarn` is not directly on `PATH`, a tiny `corepack yarn`
shim directory is prepended to `PATH` for build and test subprocesses.

## Readiness (doctor)

`doctor` probes only workspace-local locations. It deliberately never touches
unrelated home directories such as `/root/.yarn/berry/cache`, because an ordinary build
UID cannot `stat()` them and `Path.is_dir()` would raise `PermissionError`. All
filesystem probes go through `os.path.isdir`, which swallows `OSError` and reports the
candidate as unavailable instead of crashing.

The offline dependency payload is considered present if any of the following is true:

1. a hydrated yarn cache exists under `/workspace/cache/yarn` (or `YARN_CACHE_FOLDER` /
   `NPM_CONFIG_CACHE`),
2. the read-only input still ships `dependencies*.tar.gz` staging evidence,
3. the extracted source tree already has `node_modules`.

Exit codes: `0` when ready, `78` when any source/checksum/tool/dependency item is missing.

## Pipeline (`run`)

1. `prepare()` verifies the archive sha256 against `manifest.json` and extracts to `/workspace/src`.
2. `doctor` re-runs on the extracted tree; the report is written to `output/doctor_report.json`.
3. configure: `yarn install --immutable`, `make bootstrap-only`.
4. build: `make build` (the declared full baseline; all selected workspace `lib` output
   comes from this source transpilation).
5. tests: `yarn jest babel-core --ci --maxWorkers=2` and
   `TEST_ONLY=babel-parser make test-only`. Failure or empty selection aborts; nothing
   is turned into a skip.
6. package: `yarn pack` for every `packages/*` workspace into `output/install/tarballs`
   (the compiler-API dependency closure, not just `@babel/core`).
7. consume, outside `/workspace/src`:
   * `consumer-install` assembles `consumer/node_modules` from the freshly built
     tarballs (all `@babel/*` entries are replaced by this run's output) plus the
     declared external dependency closure carried over from the workspace install.
   * `transform.mjs` transpiles a fixed program containing a class, an async method and
     ESM exports for target `ie 11`, asserts the class/async syntax is gone, asserts the
     source map lists the input file, executes the emitted CommonJS output and checks the
     runtime result `[1, 2]`, and records the on-disk resolution path of every internal
     `@babel/*` package so the grader can confirm none came from a prebuilt release.
   * `negative.mjs` feeds an invalid program and requires a parse failure.
8. `Session.finish()` records commands, tests, install manifest and tarball/consumer state.

## Honest limitations

* The frozen `manifest.json` declares `offline_dependencies_ready = true`; the runtime
  hydrates the verified dependency cache into `/workspace/cache/yarn` before `doctor`
  runs, so `doctor` passes on a healthy host. If the cache is absent and no
  `dependencies*.tar.gz` staging evidence remains in the input, `doctor` reports the
  exact missing item and `run` exits 78 *before* building and never calls
  `Session.finish`; the builder stages the cache and retries. No prebuilt Babel release
  is substituted at any point.
* Jest output does not match any of `buildkit`'s numeric parsers, so case counts are left
  as `null` and the raw upstream logs are preserved verbatim instead of being invented.
* Publisher / registry operations are out of scope per the frozen contract.
* No build/test/consumer command was executed against this frozen input by the author; the
  host runs and grades it.
