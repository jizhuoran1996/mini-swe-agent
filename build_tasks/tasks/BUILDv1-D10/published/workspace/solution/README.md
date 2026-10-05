# BUILDv1-D10 - Envoy core build and qualification

Builds the official Envoy 1.34.2 static entry binary from the pinned source
archive and qualifies it with the upstream header-map unit test plus a
single-route local consumer.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input
    python3 solution/main.py run --input input --output output --jobs 4

`doctor` lists the exact missing source / tool / dependency items and exits
**78** when anything is missing, **0** when the environment is ready. `--help`
never builds.

## Pipeline (`run`)

1. `Session.prepare()` verifies the source archive sha256 and extracts it into
   `/workspace/src` (clean-directory enforced).
2. Runs the pinned Bazel 7.6.0 (`.bazelversion` checked) with the prepared
   offline caches:
   `--output_base=/workspace/cache/bazel_output`,
   `--repository_cache=/workspace/cache/bazel_repository`, `--config=clang`,
   `--jobs=4`, `--local_ram_resources=24000`, `--nofetch`, and
   `GOPROXY=off` with `HOME=/workspace/bazel-home`.
3. `bazel build -c opt //source/exe:envoy-static` (the whole large Bazel graph,
   protobuf codegen, and the final link are performed from source).
4. Packages `<output>/install`: `bin/envoy`,
   `share/envoy/config/bootstrap.yaml`, `NOTICE`, `delivery_metadata.json`.
5. `bazel test -c opt --local_test_jobs=2 --nocache_test_results
   //test/common/http:header_map_impl_test` with `ENVOY_IP_TEST_VERSIONS=v4only`
   and BEP output; the gtest pass count is parsed from the real log.
6. Runs `solution/consumer_check.py` from `/workspace/consumer` (outside the
   source tree) against the installed binary: `--version`, admin readiness, one
   static route with header propagation, and the upstream-down 503 path.
7. Runs the installed `bin/envoy --version` as a second consumer check, then
   `Session.finish()` records the install manifest and run metadata.

## Required offline inputs (checked by `doctor`)

- `source.tar.gz` matching the manifest sha256,
- Bazel 7.6.0 at `/opt/bazel/7.6.0/bazel` matching Envoy's `.bazelversion`
  (the default `bazel` 7.4.1 is **not** used for Envoy),
- `python3`, `go`, `clang`, `clang++`, `ld.lld` on `PATH`,
- hydrated Bazel dependency caches: `/workspace/cache/bazel_repository` and
  `/workspace/cache/bazel_output/external`.

The Go SDK and the Go repository sources rules_go/Gazelle consume live inside
the hydrated Bazel external graph under
`/workspace/cache/bazel_output/external`. There is **no** separate mandatory
global GOPROXY module cache: rules_go uses its hermetic Go SDK and the external
repositories, so Go tool builds only need `GOPROXY=off` and a writable `HOME`
(kept under `/workspace`). `doctor` therefore does not require a global
go-mod directory; a writable `GOMODCACHE`/`GOCACHE` is created under the
workspace at build time and is not a prebuilt input.

Missing items produce exit 78 with an explicit list; the driver never attempts
to fetch or fabricate dependencies.

## Honest limitations

- The offline Bazel repository / external caches are prepared by the builder via
  `manifest.dependency_caches`; this driver only consumes them. If they are
  absent, `doctor`/`run` exit 78 and no build is attempted.
- Only `//source/exe:envoy-static` and
  `//test/common/http:header_map_impl_test` are in scope for the core profile;
  `codec_client_test` and broader `//test/...` suites are out of scope.
- `envoy-static` is statically linked against its bundled third-party deps but
  still targets the host kernel/libc ABI; it is not a freestanding binary.
- The consumer uses IPv4 loopback only (`ENVOY_IP_TEST_VERSIONS=v4only`); IPv6
  coverage is explicitly excluded.
- If the toolchain/caches do not match the source, the build fails loudly
  (`--nofetch`), never silently falling back or reusing a prebuilt artifact.
