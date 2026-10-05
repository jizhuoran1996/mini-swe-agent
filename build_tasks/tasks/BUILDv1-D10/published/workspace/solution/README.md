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
never builds. `run` also exits 78 before doing any work if the environment is
not ready.

## Pipeline (`run`)

1. `Session.prepare()` verifies the source archive sha256 and extracts it into
   `/workspace/src` (clean-directory enforced).
2. Checks the pinned Bazel 7.6.0 against Envoy's `.bazelversion`.
3. Writes the upstream **`SOURCE_VERSION`** distribution marker (see below)
   into the extracted tree using the exact `manifest.source.commit`, and
   confirms the original `bazel/get_workspace_status` script is present.
4. Builds the full static binary from source with the prepared offline caches:

       bazel --output_base=/workspace/cache/bazel_output build \
         --repository_cache=/workspace/cache/bazel_repository --config=clang \
         --jobs=4 --local_resources=memory=24000 \
         -c opt //source/exe:envoy-static

   with `GOPROXY=off`, `HOME=/workspace/bazel-home`.
5. Packages `<output>/install`: `bin/envoy`,
   `share/envoy/config/bootstrap.yaml`, `NOTICE`, `delivery_metadata.json`.
6. `bazel test -c opt --local_test_jobs=2 --nocache_test_results
   //test/common/http:header_map_impl_test` with `ENVOY_IP_TEST_VERSIONS=v4only`
   and BEP output; the gtest pass count is parsed from the real log and empty
   discovery is treated as failure.
7. Runs `solution/consumer_check.py` from `/workspace/consumer` (outside the
   source tree) against the installed binary: `--version`, admin `/ready`,
   admin `/stats` progress evidence, one static route with header propagation,
   post-request counter accounting, and the upstream-down **503** error path.
8. Runs the installed `bin/envoy --version` as a second consumer check, then
   `Session.finish()` records the install manifest and run metadata.

## Workspace stamping on a non-git tarball

The pinned source is a tarball, not a git checkout, so Envoy's unmodified
`bazel/get_workspace_status` would invoke `git rev-parse` and fail. That script
contains an explicit distribution door:

    if [ -f SOURCE_VERSION ]
    then
        echo "BUILD_SCM_REVISION $(cat SOURCE_VERSION)"
        echo "ENVOY_BUILD_SCM_REVISION $(cat SOURCE_VERSION)"
        echo "STABLE_BUILD_SCM_REVISION $(cat SOURCE_VERSION)"
        echo "BUILD_SCM_STATUS Distribution"
        exit 0
    fi

After the archive has been sha256-verified, `write_source_version()` writes
`SOURCE_VERSION` containing the exact manifest commit
`c657e59fac461e406c8fdbe57ced833ddc236ee1` (validated as 40 lowercase hex
digits) and records the action plus its justification in
`output/source_version.json`. This exercises the original upstream branch: no
`.git` is fabricated, `BAZEL_FAKE_SCM_REVISION` is not set, `git` is not
shadowed or replaced, and no commit or status value is invented. The upstream
script file itself is left untouched.

## Bazel option placement and `--nofetch`

Only `--output_base` is a startup option and precedes the subcommand; the rest
are command options after `build`/`test`. **`--nofetch` is not passed.** It
blocks initialization of the Bazel binary's own bundled `@@bazel_tools` local
repository (a local, network-free operation). Declared external repos resolve
from the prepared repository cache and hydrated external graph. In this
`network=none` container any *genuinely missing* external dependency fails
honestly with its Bazel error - the driver does not hide it and does not
synthesize repository markers or prebuilt targets.

## Required offline inputs (checked by `doctor`)

- `source.tar.gz` matching the manifest sha256, with a manifest `source.commit`,
- Bazel 7.6.0 at `/opt/bazel/7.6.0/bazel` matching Envoy's `.bazelversion`
  (the default `bazel` is not used for Envoy),
- `python3`, `go`, `clang`, `clang++`, `ld.lld` on `PATH`,
- hydrated Bazel dependency caches: `/workspace/cache/bazel_repository` and
  `/workspace/cache/bazel_output/external`.

The Go SDK and Go repository sources rules_go/Gazelle consume live inside the
hydrated Bazel external graph under `/workspace/cache/bazel_output/external`.
There is **no** separate mandatory global GOPROXY module cache: rules_go uses
its hermetic Go SDK and the external repositories, so Go tool builds only need
`GOPROXY=off` and a writable `HOME` (kept under `/workspace`). Writable
`GOMODCACHE`/`GOCACHE` are created under the workspace at build time; they are
not prebuilt inputs.

If a declared external dependency is truly absent from the hydrated caches,
Bazel reports it and the build stops; that is a signal to complete preparation,
not something this driver masks.

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
- `SOURCE_VERSION` is a build-time distribution marker derived from the verified
  manifest commit; it is documented in `output/source_version.json`.
