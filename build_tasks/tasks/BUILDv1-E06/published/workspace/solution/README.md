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
2. `npm run clean` and `npm run build` (`hereby local` + `hereby tests`);
3. `hereby LKG` followed by `npm pack --ignore-scripts`, copying the extracted
   package layout into `<output>/install/typescript` and the `.tgz` into
   `<output>/artifacts`;
4. the frozen official compiler subset via
   `hereby runtests-parallel --light=false --tests=compiler/ --no-lint`. The
   exact discovery list of `tests/cases/compiler` is saved to
   `test_inventory.json` **before** execution and an empty discovery aborts;
5. an independent consumer: a fresh npm project outside `src/` installs the
   newly packed `.tgz` offline, `require.resolve("typescript")` must point
   inside `/workspace/consumer`, a strict generics/module project is compiled,
   its emitted JavaScript is executed (expects `{"value":42}`) with `.d.ts`
   declaration emit checked, and a separate known-bad input must fail with
   diagnostic `TS2322` and a non-zero exit code.

## Why `--no-lint`

Hereby wires the `lint` task as a sibling dependency of `runtests-parallel`.
Lint is a style gate, not compiler test evidence, and running it concurrently
with the (many) `runtests-parallel` test workers pushed the container past its
memory ceiling — the eslint child was SIGKILLed (`Process exited with code:
null`), which aborted the entire test command even though the worker batches
were still making progress. Excluding the lint task (which the build step has
already exercised) leaves the compiler test selection, discovery and results
untouched and does not weaken the frozen contract.

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
* Parallelism is capped at 4 build jobs and 2 test jobs; `-march=native` and
  unrestricted link concurrency are not used.
