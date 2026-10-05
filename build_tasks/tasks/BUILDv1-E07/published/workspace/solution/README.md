# BUILDv1-E07 - Build Rollup's JS + native parser distribution

Builds Rollup v4.40.2 from the frozen source archive using the official
`npm run build:prepare` baseline (napi native parser + Node JS distribution),
runs the official Node API test selection, packs a tarball, and independently
consumes it from outside the source tree.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor [--input input] [--output output]
    python3 solution/main.py run    --input input --output output [--jobs 4]

`--help` exits 0. `doctor` treats `--input` and `--output` as optional
(defaulting to `/workspace/input` and `/workspace/output`), never builds, and
prints the exact missing source / tool / dependency items with exit 78 on
failure or 0 when ready.

## Offline dependency caches

The manifest's `dependency_caches` entry (`dependencies.tar.gz`) is hydrated
into `/workspace/cache` on `run`. The solution then locates the prepared npm
cache (`_cacache`) and the Rust `CARGO_HOME` (`registry/cache`) anywhere under
that root or in the ambient `CARGO_HOME` / `~/.cargo`, and exports the correct
`npm_config_cache` / `CARGO_HOME` along with `CARGO_NET_OFFLINE=true` for every
build, test, packaging and install subprocess. No target release or
`node_modules` cache is copied into `output/`; the delivered artifact is only
the freshly packed tarball plus the newly built `dist/` tree inside it.

If the Rust cargo registry cache is still being prepared and cannot be found in
any of those locations, `doctor` reports it explicitly and `run` fails before
starting the build, rather than silently skipping or degrading step 2.

## Flow (run)

1. `Session.prepare()` verifies the source archive SHA-256 and extracts to
   `/workspace/src`.
2. `dependencies.tar.gz` is hydrated into `/workspace/cache` (checksum checked).
3. `npm ci --offline --ignore-scripts` installs the locked tree from the npm
   cache; ignoring scripts prevents the package prepare hook from firing early.
4. `npm run build:prepare` builds the release napi native parser and the Node
   JS distribution, then copies `rollup.*.node` into `dist/`.
5. Artifact presence is asserted (`dist/*.node`, `dist/rollup.js`,
   `dist/es/rollup.js`, `dist/bin/rollup`) before any test runs.
6. Official Node API tests: `test:only`, `test:options`, `test:package`.
   Logs are preserved verbatim; a case count is only reported when a real
   upstream summary is parsed, otherwise only raw upstream evidence remains.
7. `npm pack --ignore-scripts` produces the tarball; SHA-256 is recorded.
8. The tarball is installed into `/workspace/output/install` (INSTALL_ROOT)
   and independently into `/workspace/consumer`.
9. The consumer verifies, using only the freshly packed tarball:
   - the `.node` native parser resolves from inside the installed package's
     `dist/` (no fallback to any preinstalled `@rollup/rollup-linux-*` binary),
   - CommonJS `require('rollup')`, dynamic ESM `import('rollup')` and the CLI
     all work,
   - tree-shaking removes an unused export, a used export and a source map with
     sources survive, and the emitted bundle has correct runtime semantics
     (`answer === 49`),
   - a two-entry bundle emits a shared chunk.

## Scope and honest limitations

- CORE profile only: delivery is the Linux x86_64 native parser plus the
  ESM/CJS/CLI JS artifacts of `build:prepare`. No claim is made about WASM or
  browser bundles (`build:wasm` / full `build:js` targets are out of scope).
- `test:package` only checks package dependency metadata; it is treated as a
  metadata gate and is never a substitute for the independent consumer step.
- The devDependency Rollup used as the JS bootstrap is a build-only tool; it is
  never the delivered product. The consumer installs and loads only the newly
  packed tarball.
- Rust toolchain, `@napi-rs/cli`, the npm cache and the cargo registry cache
  must be pre-provisioned for the offline build. `doctor` reports missing ones
  instead of silently degrading or skipping any build or test step.
- Python target wheels in `/opt/wheelhouse` are not applicable to this Node
  project; isolation is achieved with a separate consumer npm tree, not a venv.
