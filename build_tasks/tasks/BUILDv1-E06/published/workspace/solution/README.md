# TypeScript v5.9.3 source-build driver

Builds the classic JavaScript TypeScript compiler package from the frozen
v5.9.3 source tree (`c63de15a992d37f0d6cec03ac7631872838602cb`), runs a
non-empty official compiler test subset, packs the npm artifact and verifies
it from a fresh consumer project outside the source tree.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

`--help` never touches the source and never builds.

`doctor` verifies, without building:

* `manifest.json` and the frozen `source.tar.gz` (exact SHA-256);
* bootstrap tools `node` (>= 14.17) and `npm`;
* the offline **npm package cache** hydrated from
  `manifest.dependency_caches` into `/workspace/cache/npm` (or an alternative
  cache directory declared under `manifest.dependencies`). A `node_modules`
  payload remains an accepted fallback but is not required when the cache is
  complete.

It prints every missing item and returns **78** when anything is missing,
**0** when the tree is ready to build.

`run` calls `Session.prepare()`, then:

1. `npm ci --offline --no-audit --no-fund --cache /workspace/cache/npm`
   against the source's own locked `package-lock.json` (no network, no
   prebuilt vendor package substituted);
2. `npm run clean` and `npm run build` (`hereby local` + `hereby tests`) —
   the genuine full compiler is compiled from source;
3. `hereby LKG` followed by `npm pack --ignore-scripts`, copying the extracted
   package layout into `<output>/install/typescript` and the `.tgz` into
   `<output>/artifacts`;
4. the frozen official compiler subset via
   `hereby runtests-parallel --light=false --tests=compiler/ --workers=2 --lint=false`.
   The exact discovery list of `tests/cases/compiler` is saved to
   `test_inventory.json` **before** execution and an empty discovery aborts;
5. an independent consumer: a fresh npm project outside `src/` installs the
   newly packed `.tgz` offline, `require.resolve("typescript")` must point
   inside `/workspace/consumer`, a strict generics/module project is compiled,
   its emitted JavaScript is executed (expects `{"value":42}`) with `.d.ts`
   declaration emit checked, and a separate known-bad input must fail with
   diagnostic `TS2322` and a non-zero exit code.

## Why `--workers=2` and `--lint=false`

`runtests-parallel`'s worker default comes from
`scripts/build/options.mjs`, which falls back to host CPU count. In this
container that reports 31 CPUs; the resulting worker pool oversubscribed
memory, a mocha worker was SIGKILLed and Hereby surfaced the whole command as
`Process exited with code: null`. Bounding the pool with `--workers=2` (and
matching `workerCount=2` in the environment, which `options.mjs` reads as the
default) keeps the run inside the frozen `test_jobs<=2` contract without
touching a single test case or baseline.

The Herebyfile also wires the style-lint task as a sibling of
`runtests-parallel`; `--lint=false` excludes only that style gate (already
exercised during the preceding `npm run build` step). No compiler test case
is filtered, skipped or re-baselined.

## Honest limitations

* The build cannot run without the offline npm cache. If the controller has
  not hydrated `/workspace/cache/npm`, `doctor` returns **78** and lists the
  exact missing item; the build, test, pack and consumer stages are wired
  end-to-end and execute unchanged once the cache is present. No prebuilt
  package is ever substituted for the target artifact.
* The classic v5.9.3 JavaScript workflow is targeted. No Go/native port, no
  cross-platform release CI, no browser test matrix.
* `buildkit.Session.test()` parses common upstream summaries; TypeScript's
  mocha runner reports `N passing / M failing`, which its parser returns as
  `null`. The raw upstream log is preserved verbatim and target-level coverage
  is reported honestly rather than manufacturing a case count.
* Parallelism is capped at 4 build jobs and 2 test workers; `-march=native`
  and unrestricted link concurrency are not used.
