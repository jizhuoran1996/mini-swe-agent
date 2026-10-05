The native release binding now builds and the COMPLETE official Rust swc_ecma_transforms --all-features tests pass. The COMPLETE upstream Node test:core runner passes 39 suites,106 tests,39 snapshots and fails its ONE plugin_analyze integration test because the nested ORIGINAL Cargo.lock needs genuine cc1.2.17 and a wasm32-wasip1 standard library. Do not disable DISABLE_PLUGIN_E2E_TESTS, skip projects/cases, change test fixtures/expected snapshots, fake modules/warnings/expect, or weaken test selection. Preserve the entire existing native/Rust/Node test scope and SDK consumer.
The trusted preparer is freezing two genuine inputs before the trial:
1) dependency_caches entry swc-plugin-dependencies.tar.gz contains the actual fetched Cargo registry closure for the upstream packages/core/e2e/fixtures/plugin_analyze/Cargo.toml. An original nested lock has stale source PATH-package versions; genuine Cargo resolution updates these without changing dependency constraints/tests. The resolved lock is supplied as input/plugin-analyze.Cargo.lock with manifest swc_plugin_fixture_lock.{filename,sha256,source_relative_destination}. Verify that frozen input hash and COPY that actual Cargo-generated lock into its declared source relative destination before testing; do not synthesize/pin alternate crate versions.
2) genuine OFFICIAL compiler bootstrap component dependency_caches entry rust-std-nightly-wasm32-wasip1.tar.xz downloaded from https://static.rust-lang.org/dist/2024-10-07/rust-std-nightly-wasm32-wasip1.tar.xz and verified against its official .sha256. Hydrator extracts it at /workspace/cache/rust-std-nightly-wasm32-wasip1. After installing the unchanged nightly-2024-10-07 compiler to /workspace/tools/swc-nightly, invoke that component's REAL install.sh with --prefix=/workspace/tools/swc-nightly --disable-ldconfig and component rust-std-wasm32-wasip1 (inspect genuine installer component listing). Do not fake rust standard libraries or use target prebuilts.
Also the official plugin test expects its real wasm output in packages/core/e2e/fixtures/plugin_analyze/target/wasm32-wasip1/debug/plugin_analyze.wasm. A global CARGO_TARGET_DIR=/workspace/src/target inherited by Node test subprocesses changes this path. Keep the genuine in-source target for the native binding/Rust Mocha tests, but for the Node official test:core command remove CARGO_TARGET_DIR from the actually inherited environment (Session.run merges with process env, so ensure unset rather than empty invalid path). The fixture Cargo workspace will then create its expected target directory normally. Keep all real Cargo/RUSTC/PATH/CARGO_HOME bindings and offline flags. Do not edit upstream test code or symlink fake expected outputs.
Implement doctor/bootstrap/frozen-dependency handling using these genuine inputs, preserving the full cold build and every functional consumer assertion.

Actual failure tail:
  ● Analysis Plugins › Emits output with plugin › Host schema version 'plugin_transform_schema_v1' › Should work with plugin schema version plugin_analyze

    thrown: 101

      84 |
      85 |                 // Put arbitrary large number for timeout to ensure test doesn't timeout due to native binaries build time.
    > 86 |                 beforeAll(async () => {
         |                 ^
      87 |                     if (!shouldUsePrebuiltHost) {
      88 |                         await buildHost(host);
      89 |                     }

      at beforeAll (e2e/plugins/plugins.analyze.test.js:86:17)
          at Array.forEach (<anonymous>)
      at e2e/plugins/plugins.analyze.test.js:75:37
      at describe (e2e/plugins/plugins.analyze.test.js:67:5)
      at Object.describe (e2e/plugins/plugins.analyze.test.js:66:1)

PASS unit tests __tests__/transform/sourcemap_test.js
  ● Console

    console.log
      "use strict";
      class Foo extends Array {
      }

      at Object.<anonymous> (__tests__/transform/sourcemap_test.js:78:13)

    console.log
      "use strict";
      Object.defineProperty(exports, "__esModule", {
          value: true
      });
      var _call_super = require("@swc/helpers/_/_call_super");
      var _class_call_check = require("@swc/helpers/_/_class_call_check");
      var _inherits = require("@swc/helpers/_/_inherits");
      var _wrap_native_super = require("@swc/helpers/_/_wrap_native_super");
      var Foo = /*#__PURE__*/ function(Array1) {
          _inherits._(Foo, Array1);
          function Foo() {
              _class_call_check._(this, Foo);
              return _call_super._(this, Foo, arguments);
          }
          return Foo;
      }(_wrap_native_super._(Array));

      at Object.<anonymous> (__tests__/transform/sourcemap_test.js:93:13)

PASS unit tests __tests__/transform/issue_4606_test.mjs
  ● Console

    console.log
      /workspace/src/packages/core/tests/issue-4606/1/index.tsx

      at Object.<anonymous> (__tests__/transform/issue_4606_test.mjs:55:13)

    console.log
      /workspace/src/packages/core/tests/issue-4606/2/index.tsx

      at Object.<anonymous> (__tests__/transform/issue_4606_test.mjs:91:13)

PASS unit tests __tests__/transform/issue_7806_test.mjs
  ● Console

    console.log
      /workspace/src/packages/core/tests/swc-path-bug-1/src/index.ts

      at Object.<anonymous> (__tests__/transform/issue_7806_test.mjs:18:17)

    console.log
      tests/swc-path-bug-1/src/index.ts

      at Object.<anonymous> (__tests__/transform/issue_7806_test.mjs:47:17)

PASS unit tests __tests__/transform/plugin_test.js
PASS unit tests __tests__/transform/issue_8701_test.mjs
  ● Console

    console.log
      baseUrl /workspace/src/packages/core/tests/issue-8701

      at Object.<anonymous> (__tests__/transform/issue_8701_test.mjs:9:13)

PASS unit tests __tests__/minify/issue_8437_test.mjs
PASS unit tests __tests__/module_test.js
PASS unit tests __tests__/transform/issue_4730_test.mjs
  ● Console

    console.log
      /workspace/src/packages/core/tests/issue-4730/src/index.ts

      at Object.<anonymous> (__tests__/transform/issue_4730_test.mjs:16:13)

PASS unit tests __tests__/dynamic_tsx.mjs
PASS unit tests __tests__/preserve_comments.mjs
PASS unit tests __tests__/transform/issue_4621_test.mjs
  ● Console

    console.log
      /workspace/src/packages/core/tests/issue-4621/1/index.tsx

      at Object.<anonymous> (__tests__/transform/issue_4621_test.mjs:18:13)

    console.log
      /workspace/src/packages/core/tests/issue-4621/1/index.tsx

      at Object.<anonymous> (__tests__/transform/issue_4621_test.mjs:49:13)

PASS unit tests __tests__/transform/issue_4734_test.mjs
  ● Console

    console.log
      /workspace/src/packages/core/tests/issue-4734/1/index.ts

      at Object.<anonymous> (__tests__/transform/issue_4734_test.mjs:18:13)

PASS unit tests __tests__/minify/issue_6996_test.mjs
PASS unit tests __tests__/parse/api_test.js
PASS unit tests __tests__/transform/hidden_jest.js
PASS unit tests __tests__/spack/simple_test.js
  ● Console

    console.log
      {
        simple: {
          code: "console.log('Foo');\n",
          map: `{"version":3,"sources":["/workspace/src/packages/core/tests/spack/simple/a.js"],"sourcesContent":["console.log('Foo')"],"names":[],"mappings":"AAAA,QAAQ,GAAG,CAAC"}`,
          diagnostics: []
        }
      }

      at Object.<anonymous> (__tests__/spack/simple_test.js:12:13)

    console.log
      {
        simple: {
          code: "console.log('Foo');\n",
          map: `{"version":3,"sources":["/workspace/src/packages/core/tests/spack/simple/a.js"],"sourcesContent":["console.log('Foo')"],"names":[],"mappings":"AAAA,QAAQ,GAAG,CAAC"}`,
          diagnostics: []
        }
      }

      at Object.<anonymous> (__tests__/spack/simple_test.js:37:13)

PASS unit tests __tests__/paths_test.mjs
PASS unit tests __tests__/minify/name_cache.test.mjs
PASS unit tests __tests__/transform/experimental.mjs
PASS unit tests __tests__/transform/issue_8491_test.mjs
PASS unit tests __tests__/transform/issue_8674_test.mjs
  ● Console

    console.log
      baseUrl /workspace/src/packages/core/tests/issue-8674

      at Object.<anonymous> (__tests__/transform/issue_8674_test.mjs:9:13)

PASS unit tests __tests__/transform/issue834_test.js
PASS unit tests __tests__/issue-9520.mjs
PASS unit tests __tests__/transform/optimizer_test.js
PASS unit tests __tests__/error_test.mjs
PASS unit tests __tests__/env/env_test.js
PASS unit tests __tests__/script_test.js
PASS unit tests __tests__/transform/issue846_test.js
PASS unit tests __tests__/transform/issue_1581_test.js
PASS unit tests __tests__/is_module_unknown_test.js
PASS unit tests __tests__/transform/swc_node_335.js
PASS unit tests __tests__/transform/issues_test.mjs
PASS unit tests __tests__/transform/issue_5325_test.mjs
PASS unit tests __tests__/import_test.js

Summary of all failing tests
FAIL e2e/plugins/plugins.analyze.test.js
  ● Analysis Plugins › Emits output with plugin › Host schema version 'plugin_transform_schema_v1' › Should work with plugin schema version plugin_analyze

    thrown: 101

      84 |
      85 |                 // Put arbitrary large number for timeout to ensure test doesn't timeout due to native binaries build time.
    > 86 |                 beforeAll(async () => {
         |                 ^
      87 |                     if (!shouldUsePrebuiltHost) {
      88 |                         await buildHost(host);
      89 |                     }

      at beforeAll (e2e/plugins/plugins.analyze.test.js:86:17)
          at Array.forEach (<anonymous>)
      at e2e/plugins/plugins.analyze.test.js:75:37
      at describe (e2e/plugins/plugins.analyze.test.js:67:5)
      at Object.describe (e2e/plugins/plugins.analyze.test.js:66:1)


Test Suites: 1 failed, 2 skipped, 39 passed, 40 of 42 total
Tests:       1 failed, 3 skipped, 106 passed, 110 total
Snapshots:   39 passed, 39 total
Time:        1.087 s
Ran all test suites in 2 projects.
