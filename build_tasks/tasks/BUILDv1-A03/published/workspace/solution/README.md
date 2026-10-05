# BUILDv1-A03 - libarchive core-profile toolchain

Source build of libarchive `v3.8.1` (`9525f90ca4bd14c7b335e2f8c84a4607b0af6bdf`)
under the frozen **core** profile: the full library plus `bsdtar`, using the
tar/zip formats and the basic compression backends (zlib, bzip2, xz/lzma, zstd).
`bsdcpio`, `bsdcat` and `bsdunzip` are out of core scope and are disabled.

## Usage

```
python3 solution/main.py doctor --input input          # 0 ready, 78 missing
python3 solution/main.py run --input input --output output --jobs 4
```

`--help` works without touching the build tree.

## What `run` does

1. `buildkit.Session.prepare()` verifies the source archive sha256 and extracts a
   clean tree into `/workspace/src`.
2. CMake configure (`Release`, private install prefix, `ENABLE_TEST=ON`,
   `ENABLE_TAR=ON`), build with `BUILD_JOBS` (<=4). Every `CMAKE_INSTALL_*`
   component directory (`LIBDIR`, `BINDIR`, `INCLUDEDIR`, `PKGCONFIGDIR`,
   `MANDIR`, ...) is pinned to a prefix-relative value on the command line
   **and** in the environment, because the container exports an empty
   `CMAKE_INSTALL_LIBDIR` which otherwise makes libarchive derive an absolute
   `/pkgconfig` install destination. Pkg-config support stays enabled and the
   installed `lib/pkgconfig/libarchive.pc` is asserted; a guard fails the run if
   anything appears at `/pkgconfig`.
3. `ctest -N` is recorded as the official test inventory **before** execution.
4. `ctest --output-on-failure --parallel 2` runs the upstream suite; the log and
   parsed CTest summary are preserved in `output/tests.json` and `output/logs/`.
5. `cmake --install` into `output/install`, followed by an existence check for
   `bin/bsdtar`, `include/archive.h`, `lib/libarchive.so*` and
   `lib/pkgconfig/libarchive.pc`.
6. Independent consumption from `/workspace/consumer` (never the source tree):
   - `bsdtar` creates `fixture.tar.gz` (subdirectory, 64 KiB member, symlink,
     hardlink, mode 0640) and `fixture.zip`;
   - both archives are extracted and byte-compared; symlink target, hardlink
     inode identity and the restored mode are asserted;
   - a truncated (corrupt) archive must make `bsdtar` exit non-zero;
   - `solution/consumer.c` is compiled with `-I/-L` against the install prefix
     and `-Wl,-rpath` to `output/install/lib`, then enumerates the archive
     through `archive_read_*`, recomputing FNV-1a digests of every member;
   - the same consumer must reject the corrupt archive and a missing archive.

## Directory-name normalisation

Upstream tar readers may expose a directory member as either `data` or
`data/`. The harness folds an optional single trailing slash when looking up a
member (`_norm`), then still asserts the archive-entry type is a directory and
independently verifies every regular-file payload, size, FNV-1a digest and both
link targets. Directory verification is therefore retained, not weakened.

## Honest limitations

- Core profile only: `bsdcpio`/`bsdcat`/`bsdunzip` are configured off by design,
  so their CTest registrations are not part of this deliverable.
- ACL/XATTR support is left at the upstream default (no capability was toggled
  to make a test pass). If the reference filesystem lacks the required
  capabilities, the corresponding upstream tests fail honestly instead of
  being skipped by this harness.
- Only target-relevant `tools:`/`dependency:` headers are checked by `doctor`;
  a missing compression header returns 78 rather than silently building with a
  reduced backend set.
- No wheel/venv step applies: this is a C/CMake project, so the consumer is a
  compiled binary linked against the new install prefix.
- Optional source patching / `bsdcpio` (reference scope) is intentionally not
  exercised, mirroring the frozen core contract.
