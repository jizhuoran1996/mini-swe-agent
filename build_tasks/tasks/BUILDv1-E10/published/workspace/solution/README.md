# BUILDv1-E10 - SWC core native Node bindings (frozen core profile)

Source-grounded build driver for the frozen SWC release
`v1.11.24` @ `d7932596f2b1c99d04b9a8911d69458ed149ae59`.

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
2. Offline configure of the JS workspace lockfile with the detected package
   manager (the pinned Yarn 4.0.2 via Corepack, or pnpm/npm if that is what the
   workspace provides).  `YARN_ENABLE_NETWORK=0` and the offline cache folder
   (default `/workspace/cache/yarn`) keep this strictly hermetic.
3. `run build` -> `packages/core` -> `tsc -d` plus the napi **release** build of
   `-p binding_core_node`, producing a fresh `swc.linux-x64-gnu.node`.
   The `napi` CLI is consumed as a normal workspace devDependency through
   `node_modules/.bin` (invoked by the package scripts via `yarn run` / `npx
   --no-install`); no global `napi` binary is required.
4. Staging of the local bundle (JS + `.d.ts` + `package.json` + the new `.node`)
   into `output/install`, exactly matching `binding.js`'s local loading layout.
   A plain `npm pack` is *not* sufficient: the published `files` list drops the
   local `.node`.
5. Official, bounded, non-empty test selection with preserved evidence:
   `cargo test --offline --locked -p swc_ecma_transforms --all-features` and the
   `packages/core` rstest suite (`yarn run test:core`).
6. Independent consumer **outside the source tree** that resolves `@swc/core`
   purely from `INSTALL_ROOT`: it asserts the loaded directory is inside the
   install root, hashes the real `.node`, transpiles TypeScript to a declared
   ES target, executes the emitted CommonJS, checks source-map mappings, and
   confirms an invalid-syntax diagnostic is raised.
7. `Session.finish()` only after real installed files and non-empty test evidence
   exist.

## Honest limitations

* This profile targets **linux-x86_64-gnu** only.  No cross-platform CI matrix,
  no WASM plugin build, no other-arch native binaries.
* The build runs entirely **offline**.  It refuses to substitute any preinstalled
  `@swc/core-linux-*` release package or an old `target/` cache for the freshly
  built artifact.
* When the cargo registry cache (default `/workspace/cache/cargo`) and/or the JS
  package cache are absent, `run` exits `78` with `output/unmet_dependencies.json`
  rather than pretending to succeed.  `doctor` reports the same items up front,
  so a prepared cache can be checked and the command retried.
* The frozen `.gitmodules` submodules are present in the source archive and are
  used by the selected tests; they are not fetched at run time.
* Case counts are only reported where the upstream runner emits a recognizable
  summary; otherwise the detailed upstream log is preserved verbatim and no case
  count is invented.
