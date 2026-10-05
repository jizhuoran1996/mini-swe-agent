# BUILDv1-A09 - nghttp2 CORE-profile source build

Builds the full libnghttp2 C library from the frozen v1.65.0 source release
(commit 319bf015de8fa38e21ac271ce2f7d61aa77d90cb), producing shared and static
artifacts plus an installed development package, running the official upstream
main and failmalloc tests, and independently consuming the built library from
outside the source tree.

## CORE vs reference profile

The frozen CORE profile is deliberately narrower than the reference spec:

- ENABLE_LIB_ONLY=ON gives library only. The reference profile additionally
  builds the nghttp/nghttpd/nghttpx/h2load applications and performs a local
  HTTP/2 loopback transfer.
- Applications, HPACK tools and examples are OFF; static + shared libraries
  and the main / failmalloc tests are ON (BUILD_TESTING requires
  BUILD_STATIC_LIBS, so both are forced on).
- HTTP/3, eBPF and mruby are OFF.

Consumer verification for CORE is the HPACK deflate/inflate round trip: a
standalone C program (compiled and executed under /workspace/consumer, i.e.
outside the source tree) round-trips fixed header fields through
nghttp2_hd_deflate_* and nghttp2_hd_inflate_hd2 against the freshly installed
library and asserts exact order and content.

## Usage

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input
    python3 solution/main.py run --input input --output output --jobs 4

run first re-checks the input set. If anything is missing it writes
output/doctor.json and exits 78 without building, so a missing dependency is
never silently downgraded to a skip.

## Honest limitations

- The upstream tests/munit directory is a git submodule. A codeload source
tarball does not contain submodules, so with the frozen
  offline_dependencies_ready=false state the main/failmalloc tests cannot be
  compiled until pre-acquired munit content is provided. doctor reports this
  specific item and the builder must re-run after preparing it.
- No network access is used at any point; no system nghttp2 is substituted for
  the freshly built one.
- Only the CORE scope is delivered. App-level HTTP/2 loopback verification
  belongs to the reference profile and is intentionally absent here.
