# BUILDv1-B10 - OpenJDK 21 server image source build

Builds the frozen OpenJDK 21.0.7+6 source release (jdk21u commit
`4215779271750e6409bdfbd6d94d16002bd9b6a7`, sha256
`1888a5b967240efc83d3786667af1b3b8f75de5646c96c39bfccc9e331d9e5e9`) into a
distributable server JDK image, runs the official `jdk_lang` jtreg group with
the hydrated `jtreg 7.3.1+1` harness, and consumes the freshly built JDK
outside the source tree (javac/java/jar plus a JNI shared library).

## Commands

```
python3 solution/main.py doctor --input input --output output
python3 solution/main.py run --input input --output output --jobs 1
```

`doctor` exits `0` when every required source/tool/dependency is present and
`78` (EX_CONFIG) otherwise, printing the exact missing items as JSON. It never
builds. `run` performs the same gate first and exits `78` before touching the
build tree if anything is missing. `--help` works with no build.

## Fixes retained

### 1. `JAVA_TOOL_OPTIONS` / `_JAVA_OPTIONS` must not reach configure

Upstream OpenJDK configure aborts if `_JAVA_OPTIONS` or `JAVA_TOOL_OPTIONS` is
set. Every session command is launched as
`/usr/bin/env -u JAVA_TOOL_OPTIONS -u _JAVA_OPTIONS <real argv...>` so those
variables are gone regardless of the container environment. Thread bounding
uses only upstream-supported knobs.

### 2. PID exhaustion under the old `--with-jobs=2` cold build

jdk21u enables the javac-server by default, so each compiled module spawned its
own javac daemon plus worker threads while hotspot's parallel back-end
compilation also spawned multiple compile processes; `fork` then failed with
`Resource temporarily unavailable` at the cgroup PID ceiling. The supported
option `--disable-javac-server`
(`make/autoconf/build-performance.m4`) removes those daemons, and
`--with-jobs=1 --with-num-cores=1` plus `make JOBS=1` keep the process count
bounded. This combination is now known to complete a full `images` build here
with no fork exhaustion. `--with-boot-jdk-jvmargs` (which the makefiles thread
into *every* build-time java/javac launch) bounds the boot JVM with
`-XX:ActiveProcessorCount=1 -XX:ParallelGCThreads=1 -XX:ConcGCThreads=1`.

### 3. The configure-selected output directory (why the previous run failed)

`make CONF=release images` was run with `cwd=/workspace/src`, so OpenJDK
produced its image under the SOURCE tree at
`/workspace/src/build/release/images/jdk` (the location selected by configure
`--with-conf-name=release`). The previous code looked in the generic
`/workspace/build/release/images/jdk` (Session.build) and failed. This version
reads `OUTPUTDIR` / `IMAGES_OUTPUTDIR` from the generated
`src/build/release/spec.gmk` and falls back to scanning
`src/build/*/images/jdk`; the resulting path is recorded in
`output/built_image_location.json`. No boot JDK and no fabricated path is ever
used. `output/configure_evidence.json` records what configure actually chose
(`selected_outputdirs`, `BOOT_JDK_JVMARGS`, `JAVAC_SERVER_ENABLED`).

## Pipeline

1. `prepare()` verifies the archive sha256 and safely extracts to `/workspace/src`.
2. configure (see above), then spec.gmk evidence + output-dir discovery.
3. `make CONF=release JOBS=1 images`.
4. The discovered `src/build/release/images/jdk` is copied verbatim to
   `output/install` and repacked as `output/openjdk-image.tar.gz`.
5. Consumers outside the source tree using only the new JDK: a version check
   that asserts the delivered image reports the source version (`21.0.7`, from
   the manifest `release_ref`), ruling out the boot JDK false-pass, then
   `javac`/`jar`/`java` on an application exercising collections, threads and
   file IO, then `javac -h` + `gcc` for a JNI shared library loaded by the new
   JVM.
6. Official tests (never replaced by a smoke test).
7. `finish()` writes `install_manifest.json`, `install.tar.gz` and the run
   record.

## Output artefacts

- `output/install/` - the full JDK image; `output/openjdk-image.tar.gz`.
- `output/logs/*.log` - full stdout/stderr of every command.
- `output/commands.json`, `output/tests.json`.
- `output/dependencies.json`, `output/configure_evidence.json`,
  `output/environment_evidence.json` (cgroup PID/memory/CPU snapshots before
  and after the build).
- `output/built_image_location.json` - the exact, configure-derived image path.
- `output/jdk_lang_inventory.json` - the test-source inventory that
  `make test TEST=jdk_lang` will discover, saved before execution.
- `output/jtreg_summary.json` - the parsed upstream `Test results:` line.

## Honest limitations

- `buildkit.test()`'s built-in parsers recognise pytest/gtest/ctest/unittest/
  junit/dejagnu/TAP summaries; jtreg instead prints
  `Test results: passed: N; failed: M; error: K`. So when the built-in parser
  returns `null` the raw upstream log is preserved under `output/logs` and the
  run reports honest target-level coverage - no case count is invented. The
  genuine jtreg summary is additionally parsed from that same raw log into
  `jtreg_summary.json`; if it reports failures or errors the run fails.
- Wall time depends on the PID-bounded parallelism (`JOBS=1`, javac-server
  disabled); that is a configuration choice for this cgroup, not a measured
  performance figure.
- Only Linux x86_64 server HotSpot is produced; other JVM variants and
  cross-platform CI tiers are out of scope for the `core` profile.
- The base-image boot JDK is a dependency input, distinct from the newly built
  target JDK delivered under `output/install`.
