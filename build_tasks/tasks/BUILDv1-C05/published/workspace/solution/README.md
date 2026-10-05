# BUILDv1-C05 - OpenCV 4.11.0 CPU core SDK

Source-built delivery for the frozen **core** profile of OpenCV 4.11.0
(commit `31b0eeea0b44b370fd0712312df4214d4ae1b158`).

## Scope actually built

* Modules: `core`, `imgproc`, `imgcodecs`, `ts`.  Nothing removed.
* Shared libraries (`BUILD_SHARED_LIBS=ON`), Release build, Ninja generator.
* `BUILD_TESTS=ON`, `BUILD_PERF_TESTS=OFF`, no Python/Java bindings,
  no CUDA/OpenCL/IPP/TBB/FFMPEG/GStreamer/GTK/Qt.
* Bundled `libjpeg`, `libpng`, `libtiff`, `zlib` are compiled from the
  in-tree `3rdparty` sources so no network access is required.
* Stack protector and all upstream test expectations are untouched.

## Commands

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input      # exit 78 if anything is missing
python3 solution/main.py run --input input --output output --jobs 4
```

All build, install, test and consumer commands run through
`buildkit.Session` (`.prepare`, `.run`, `.test`, `.write`, `.finish`), so
every exit code and log is preserved under `output/logs/` and summarised
in `output/commands.json` and `output/tests.json`.

## Official accuracy tests

The following official binaries are executed from `build/bin`:

* `opencv_test_core`
* `opencv_test_imgproc`
* `opencv_test_imgcodecs`

A gtest XML report per binary is written to the absolute path
`<output>/xml/<name>.xml`.  `tests.json` records the parsed
`[  PASSED  ] N tests` count from each real run.  If
`opencv_extra/testdata` is present on the input mount,
`OPENCV_TEST_DATA_PATH` is set to it.

## Bounded diagnostic: the stack-smash loop

### Observed

A full run of `opencv_test_core` reached `BufferArea.bad/1`
(`GetParam()==false`) and then emitted roughly **7.9 GB** of repeating
`*** stack smashing detected ***: terminated` lines, until the 128 MiB
per-command log cap killed the process (`exit -9`).  The full lossless
log was retained before the fix.

### Root cause

* `BufferArea.bad` calls `BufferArea::allocate` with a deliberately bad
  size / alignment / non-zero pointer, expecting `EXPECT_ANY_THROW`.
  Under `GetParam()==false` the safe path is off; the exact upstream
  behaviour here is a stack-canary abort, not a C++ exception.
* `modules/ts/src/ts.cpp` installs a SIGABRT handler gated on
  `::testing::GTEST_FLAG(catch_exceptions)` (lines 293 and 565).  That
  handler is built on `setjmp`/`longjmp`.  When the glibc stack checker
  raises `SIGABRT`, the handler catches it, `longjmp` re-enters the same
  failing stack frame, the canary check fires again, and the cycle
  repeats without bound.

### Supported fix

OpenCV's `ts` module ships a copy of gtest plus the option
`--gtest_catch_exceptions=0`, implemented in
`modules/ts/src/ts_gtest.cpp` and read through
`GTEST_FLAG(catch_exceptions)` in `ts.cpp`.  Passing it removes the
recursive longjmp handler so the **first** signal is reported once and
terminates the process.  We pass it as an argument *and* export
`GTEST_CATCH_EXCEPTIONS=0` for redundancy:

```
opencv_test_core --gtest_catch_exceptions=0 --gtest_color=no \
                 --gtest_output=xml:/abs/path/opencv_test_core.xml
```

### What this does NOT do

* It does **not** skip `BufferArea.bad` - it still runs and its result is
  retained.
* It does **not** change any expectation, filter, or test list.
* It does **not** disable the stack protector.
* It does **not** remove any module or any case.
* It does **not** turn a failure into a pass: if the first exposed signal
  is a genuine upstream defect at the pinned revision, it is reported
  honestly through the exit code and the retained log.

If later investigation shows the pinned revision must be replaced, that
would have to be proposed explicitly with a new pinned revision rather
than silently changed here.

## Diagnostic binary snapshot (`output/diagnostic/`)

The exact upstream test binaries that produced the retained failure logs
are copied to `<output>/diagnostic/` (with sizes and SHA-256 in
`<output>/diagnostic_binaries.json`) **before** the suites run.  They are
additional evidence for offline investigation of the original core
fault without a rebuild.  They live outside `output/install/`, so they are
never part of the delivered SDK and cannot be confused with it.

## Installed tree and consumer

The build installs a complete CMake package at
`output/install/lib/cmake/opencv4`.  A small consumer project is written
to `/workspace/consumer`, configured with an explicit
`-DOpenCV_DIR=<install>/lib/cmake/opencv4` (never a system OpenCV), linked
only against the freshly built shared libraries, and executed with
`LD_LIBRARY_PATH=<install>/lib`.  It asserts meaningful semantics: PNG
`imencode`/`imdecode` round-trip within NORM_INF <= 1, red-region pixel
counts from an `inRange` mask, Canny edge density, resize dimensions, and
writes the resulting images under `/workspace/consumer/out`.

## Honest limitations

* Only the **core** profile modules are built.  Feature matching,
  calibration, video and ML APIs from the broader reference design are
  intentionally out of scope here.
* The consumer exercises image-processing and codec paths, not the
  feature-matching/registration pipeline named in the reference design,
  because those modules are not part of the frozen core build.
* `opencv_extra` test data is not required by construction; when it is
  absent only the data-independent core/imgproc/imgcodecs checks are
  actually exercised, which is reflected in the per-binary
  passed/skipped counts rather than reported as full coverage.
* If `opencv_test_core` still terminates on a real first signal at
  `BufferArea.bad/1`, that is a genuine upstream conclusion at this
  pinned revision and is reported as such; the pinned source is not
  altered and no test expectation is modified.
* No timing, memory or I/O measurements are claimed; the reference
  measurements in the specification remain `null`.
