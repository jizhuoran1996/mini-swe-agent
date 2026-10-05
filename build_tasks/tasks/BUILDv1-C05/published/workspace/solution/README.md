# BUILDv1-C05 - OpenCV 4.11.0 CPU core SDK

Source-built delivery for the frozen **core** profile of OpenCV 4.11.0
(commit `31b0eeea0b44b370fd0712312df4214d4ae1b158`).

## Scope built

* Bundled from the pinned upstream archive: `core`, `imgproc`,
  `imgcodecs`, `ts`. Nothing removed, nothing filtered, nothing skipped.
* Shared libraries (`BUILD_SHARED_LIBS=ON`), Release, Ninja generator.
* `BUILD_TESTS=ON`, `BUILD_PERF_TESTS=OFF`. Bindings and optional
  backends disabled (no CUDA/OpenCL/IPP/TBB/FFMPEG/GStreamer/GTK/Qt)
  because the frozen container has no network and no GPU.
* Bundled `libjpeg`, `libpng`, `libtiff` from the in-tree `3rdparty`
  sources so configure/build never hit the network.
* Every codec feature and every upstream test expectation remains
  untouched.

## Zlib / OpenEXR linkage

The first replay linked `opencv_imgcodecs` at 553/618 objects, then
failed with:

```
/usr/bin/ld: cannot find zlib: No such file or directory
```

The tail of the link line showed a **bare** `zlib` token appended after
`libIex-3_1.so.30.5.1`. That bare name is emitted by the Debian-packaged
`OpenEXRConfig.cmake`, whose `find_dependency(ZLIB)` sees a cached
`ZLIB_LIBRARY` that OpenCV had already overwritten with the **name** of
its internal bundled-zlib target (because we configured
`-DBUILD_ZLIB=ON`). The string `zlib` is meaningless to the linker.

Corrected by using the genuine preinstalled system zlib uniformly:

```
-DBUILD_ZLIB=OFF
-DZLIB_LIBRARY=/usr/lib/x86_64-linux-gnu/libz.so
-DZLIB_LIBRARIES=/usr/lib/x86_64-linux-gnu/libz.so
-DZLIB_INCLUDE_DIR=/usr/include
-DZLIB_ROOT=/usr
-DCMAKE_PREFIX_PATH=/usr
```

Now `find_package(ZLIB)` (CMake 3.28 FindZLIB) resolves the standard
`ZLIB::ZLIB` imported target for every consumer -- PNG, TIFF, OpenEXR,
Imath -- and the link line carries the real shared object. The library
is discovered dynamically (`ctypes.util.find_library("z")` first, then a
bounded `<root>/libz.so*` scan). Nothing is fabricated: when the system
zlib or its header is absent both `doctor` and `run` refuse with exit
code 78 and an explicit `MISSING:` line.

No codec was disabled (`BUILD_JPEG/PNG/TIFF=ON`), no source or CMake
test was patched, and `libopencv_imgcodecs.so` links the full
grfmt set: AVIF, BMP, EXR, GDAL, GDCM, GIF, HDR, JPEG, JPEG2000 (OpenJPEG
and Jasper paths), JPEG-XL, PAM, PFM, PNG, PXM, SunRaster, TIFF, WEBP.

## Commands

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input      # exit 78 if unavailable
python3 solution/main.py run --input input --output output --jobs 4
```

All build / install / test / consumer commands run through
`buildkit.Session` (`.prepare`, `.run`, `.test`, `.write`, `.finish`), so
`output/logs/`, `output/commands.json` and `output/tests.json` preserve
every exit code, SHA-256 and log.

## Official accuracy tests

Executed from `build/bin` with an absolute XML output path:

* `opencv_test_core`
* `opencv_test_imgproc`
* `opencv_test_imgcodecs`

```
opencv_test_* --gtest_catch_exceptions=0 --gtest_color=no \
              --test_data_path=<opencv_extra/testdata> \
              --gtest_output=xml:<abs output>/xml/opencv_test_*.xml
```

### Bounded diagnostic: the stack-smash catch-loop

`BufferArea.bad/1` (GetParam=false) calls `BufferArea::allocate` with a
deliberately bad size / alignment / nonzero pointer, expecting
`EXPECT_ANY_THROW`. `modules/ts/src/ts.cpp` installs a SIGABRT handler
gated on `::testing::GTEST_FLAG(catch_exceptions)` (lines 293 and 565)
built on `setjmp`/`longjmp`. When the glibc stack checker raises
`SIGABRT`, the handler catches it, `longjmp` re-enters the failing stack
frame, the canary check fires again, and the cycle repeats without
bound - roughly 7.9 GB of repeating `*** stack smashing detected ***`
lines until the 128 MiB per-command log cap killed the process.

The **real, source-documented** fix is the option implemented by the
bundled gtest copy in `modules/ts/src/ts_gtest.cpp`:

```
--gtest_catch_exceptions=0
```

The `GTEST_CATCH_EXCEPTIONS=0` environment variable is exported in
addition. With it the first signal is reported once and the process
terminates; `BufferArea.bad/1` then runs to a normal PASS.

What this does **not** do:

* It does not skip, filter, or exclude `BufferArea.bad` or any case.
* It does not change any expectation or any upstream test source.
* It does not disable the stack protector or edit `ts.cpp`.
* It does not turn a failure into a pass: any remaining upstream signal
  is reported honestly through the exit code and retained logs.

The invented `--test_system_exception_handling=0` flag from the earlier
replay is not a real option in 4.11 and is not used.

## Official test data (opencv_extra, mandatory)

`manifest.opencv_official_testdata` locks opencv_extra tag 4.11.0 commit
`a74cf6bae7fd75d91282b877c559168b3a62148a`, hydrated at
`/workspace/cache/opencv_extra/testdata`. That is used verbatim as both
`OPENCV_TEST_DATA_PATH` and `--test_data_path=<dir>`.

A directory is only accepted if it really is an upstream testdata tree,
i.e. it contains a `cv/` subdirectory. `_find_test_data` looks in this
order at the manifest-declared path, the `dependency_caches` destination,
`$OPENCV_TEST_DATA_PATH`, the canonical `/workspace/cache` locations,
input-mount paths, then a bounded `rglob("testdata")`, then finally
extracts any staged `opencv_extra*.tar*` bundle. **Nothing is ever
synthesised**: no `lena`, no `cv/io` base64 fixtures, no baseline images
are created. If the tree cannot be found the affected cases fail and the
run exits non-zero with the exact selectors recorded in
`official_test_failures.json`.

`doctor` probes the declared testdata paths and reports
`MISSING: official opencv_extra/testdata not hydrated ...` with exit 78
when the `cv/` subtree is absent, alongside source-archive hash, tool,
and system-zlib checks.

## Diagnostic binary snapshot (`output/diagnostic/`)

Before running the suites, the exact upstream test binaries are copied to
`<output>/diagnostic/` with bytes and SHA-256 recorded in
`<output>/diagnostic_binaries.json`. This is additional evidence for
offline investigation of the original core fault **without rebuilding**.
They live **outside** `output/install/`, so they can never be mistaken
for the delivered SDK.

## Consumer

A small project is written to `/workspace/consumer`, configured with an
explicit `-DOpenCV_DIR=<install>/lib/cmake/opencv4` (never a system
OpenCV), linked only against the freshly built shared libraries and run
with `LD_LIBRARY_PATH=<install>/lib`. It asserts:

* PNG `imencode` / `imdecode` round-trip within `NORM_INF <= 1`.
* red-region pixel count from an `inRange` mask.
* Canny edge density.
* resize output dimensions.
* writes `consumer_original.png`, `consumer_mask.png`,
  `consumer_edges.png` under `/workspace/consumer/out`.

## Honest limitations

* Only the frozen **core** profile modules are built
  (`core`/`imgproc`/`imgcodecs`/`ts`). Feature matching, calibration,
  video and ML APIs from the broader reference design are out of scope
  for this instance.
* The consumer exercises image processing and codec paths, not a
  feature-matching / registration pipeline, because those modules are
  not part of the frozen core build.
* If a later official pinned release were ever required, it would be
  proposed explicitly rather than silently swapping the source: the
  frozen 4.11.0 commit is used as-is.
* No timing, memory, or I/O measurements are claimed; the reference
  measurements in the specification remain `null`.
