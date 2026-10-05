# esbuild core builder

Builds esbuild v0.25.4 native CLI from the frozen source archive, runs the official Go tests, installs `bin/esbuild`, and runs an independent CLI consumer outside the source tree.

Usage:

```sh
python3 solution/main.py --help
python3 solution/main.py doctor --input /workspace/input
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` returns 78 if any required source, tool, or dependency item is missing; it returns 0 when ready. It checks the source archive checksum and required archive files, `make`, `go`, `node`, and whether the installed Go version satisfies the `go` directive in the source `go.mod`.

Scope, frozen core profile:

- Linux x86_64 native Go binary built from source.
- Official test selector: `make test-go`.
- Independent consumer: bundles a fixed TS/JS multi-module program with the installed binary, executes the bundle, checks metafile inputs, and verifies negative syntax/import errors.
- Does not build the JS adapter, browser/wasm/deno targets, or run `make test-all`.
- Offline behavior: `GOPROXY=off`, `GOTOOLCHAIN=local`, no network package downloads.
- Installed artifact: `/workspace/output/install/bin/esbuild`.

Honest limitations:

- The consumer exercises the CLI, not the Node service API adapter.
- Cross-platform npm release builds and platform-specific binary packages are out of scope for this profile.
- If the available Go toolchain is older than the source `go.mod` requirement, the run fails honestly with return code 78 from `doctor`/preflight.
