# BUILDv1-E10 - SWC core native Node bindings (frozen core profile)

Source-grounded build driver for the frozen SWC release
`v1.11.24` @ `d7932596f2b1c99d04b9a8911d69458ed149ae59` (linux-x86_64-gnu).

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input          # 0 = ready, 78 = missing items
python3 solution/main.py run --input input --output output --jobs 4
```

`--help` never touches the source archive.  `doctor` prints the exact missing
source / tool / dependency items and exits `78` when any are absent, `0` when the
frozen build can actually start.

## What `run` performs

1. `Session.prepare()` verifies the frozen archive sha256 and extracts it into
   `/workspace/src` (refuses non-empty source/build/install roots).
2. **Bootstrap** (`phase=bootstrap`): the pinned genuine Rust release is installed
   with its own official installer
   (`/workspace/cache/rust-nightly-x86_64-unknown-linux-gnu/install.sh`), invoked
   with `--components=rustc,cargo,rust-std-x86_64-unknown-linux-gnu
   --disable-ldconfig --without=rust-docs` and `--prefix=/workspace/tools/swc-nightly`.
   `rustc --version`, `cargo --version` and `rustc -vV` are then run from the
   installed toolchain.  No version is faked and `RUSTC_BOOTSTRAP` is unset.
3. **Toolchain binding.**  `/workspace/tools/swc-nightly/bin` is a fixed install
   prefix, so it is prepended to `PATH` for both the bootstrap and every later
   step; after installation the environment is *rebuilt* and the genuine
   `RUSTC` / `CARGO` paths are exported.  The `napi` release build of
   `binding_core_node` and every official Cargo test subprocess resolve the pinned
   `nightly-2024-10-07` rustc (which accepts `-Zshare-generics`), never a stable
   rustc.
4. Offline configure of the frozen JS workspace (`yarn install --immutable
   --mode=skip-build` with `YARN_CACHE_FOLDER=/workspace/cache/yarn`,
   `YARN_ENABLE_NETWORK=0`), followed by the preset-env data copy step.  The
   `napi` CLI is consumed strictly as a `node_modules` devDependency; no global
   `napi` binary is required.
5. `yarn run build` -> `packages/core` -> `tsc -d` plus the napi **release** build
   of `-p binding_core_node`, producing a fresh `swc.linux-x64-gnu.node`.
6. Staging of the local bundle (JS, `.d.ts`, `package.json` and the new `.node`)
   into `output/install`, matching `binding.js`'s local loading layout, plus the
   runtime JS dependencies so the bundle is self-contained.  A plain `npm pack` is
   *not* sufficient: the published `files` list drops the local `.node`.
7. Official, bounded, non-empty test selection with preserved evidence:
   `cargo test --offline --locked -j 2 -p swc_ecma_transforms --all-features` and
   the `packages/core` rstest suite (`yarn run test:core`), both executed with the
   bound nightly `RUSTC`/`CARGO`.
8. Independent consumer **outside the source tree** that loads `@swc/core` only
   from `INSTALL_ROOT` (`require(path.join(INSTALL_ROOT, 'index.js'))`), asserts the
   resolved entry is inside the install root, hashes the real `.node`, transpiles
   TypeScript to a declared ES target, executes the emitted CommonJS, checks
   source-map mappings, confirms an invalid-syntax diagnostic is raised and that
   `minifySync` returns output.
9. `Session.finish()` only after real installed files and non-empty test evidence
   exist.

## Cargo target directory is intentionally INSIDE the checkout

The official `swc_ecma_transforms_testing` harness spawns a **genuine Mocha child**
for the `*_exec` fixture cases (see
`crates/swc_ecma_transforms_testing/src/lib.rs`, `run_node_test_runner`), with a
working directory below `CARGO_TARGET_DIR`.  Mocha discovers its configuration
through ancestor traversal from that cwd, so it only sees the *unmodified official*
`./.mocharc.js` (which `require`s `./.mocha.setup.js`) when the target directory
lives inside the checkout.  Pointing `CARGO_TARGET_DIR` outside the source tree
(such as `/workspace/build/cargo-target`) strips that official environment and all
`*_exec` decorator cases fail with `ReferenceError: expect is not defined`.

This driver therefore uses the upstream default location `<src>/target`.  No fake
`expect`/`assert` globals, no replacement `--require` hook, no wrapper harness and
no fixture or assertion edits are used - the genuine official setup supplies the
test environment.

## Honest limitations

* This profile targets **linux-x86_64-gnu** only.  There is no cross-platform CI
  matrix, no WASM plugin build, and no other-arch native binary.
* The build runs entirely **offline**.  It refuses to substitute any preinstalled
  `@swc/core-linux-*` release package or an old `target/` cache for the freshly
  built artifact; the consumer proves this by resolving the entry point directly
  inside `INSTALL_ROOT`.
* `doctor` reports missing items and `run` exits `78` with
  `output/unmet_dependencies.json` when the offline cargo registry
  (`/workspace/cache/cargo`) and/or the Yarn cache are absent.  It never fabricates
  success.
* The frozen `.gitmodules` submodules are shipped inside the source archive and are
  used by the selected tests; they are not fetched at run time.
* Case counts are reported only where the upstream runner emits a recognizable
  summary; otherwise the detailed upstream log is preserved verbatim and no case
  count is invented.
* The bootstrapped toolchain is installed under `/workspace/tools`; the hydrated
  installer directory may be removed afterwards to reclaim workspace space, but the
  read-only `input/` archive is always preserved.
