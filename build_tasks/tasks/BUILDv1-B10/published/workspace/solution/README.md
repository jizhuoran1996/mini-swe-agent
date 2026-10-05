# BUILDv1-B10 - OpenJDK 21 server image source build

Builds the frozen OpenJDK 21.0.7+6 source release (`jdk21u` commit
`4215779271750e6409bdfbd6d94d16002bd9b6a7`, sha256
`1888a5b967240efc83d3786667af1b3b8f75de5646c96c39bfccc9e331d9e5e9`) into a
distributable server JDK image, runs the official `jdk_lang` jtreg group with
the hydrated `jtreg 7.3.1+1` harness, and consumes the freshly built JDK
outside the source tree.

## Commands

```
python3 solution/main.py doctor --input input --output output
python3 solution/main.py run --input input --output output --jobs 2
```

`doctor` exits `0` when every required source/tool/dependency is present and
`78` (EX_CONFIG) otherwise, printing the exact missing items as JSON. It never
builds. `run` performs the same gate first and exits `78` before touching the
build tree if anything is missing, so a failed gate never leaves a partial
image behind. `--help` works with no build.

## Fix for the observed configure failure

Upstream OpenJDK configure aborts with

```
configure: You have _JAVA_OPTIONS or JAVA_TOOL_OPTIONS set. This can mess up
the build. Please use --with-boot-jdk-jvmargs instead.
configure: error: Cannot continue
```

The previous version passed `JAVA_TOOL_OPTIONS` to every child process in order
to bound JVM threads; that is exactly what configure forbids. Now:

- `JAVA_TOOL_OPTIONS` and `_JAVA_OPTIONS` are **explicitly removed** from every
  child environment: each session command is launched as
  `/usr/bin/env -u JAVA_TOOL_OPTIONS -u _JAVA_OPTIONS <real argv...>`, so the
  variables are gone regardless of what the container environment contains.
- Thread bounding uses the **supported** upstream mechanisms only:
  `--with-boot-jdk-jvmargs="-XX:ActiveProcessorCount=2 -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1"`,
  `--with-jobs=2`, `--with-num-cores=2`, `make ... JOBS=2`, and for the official
  run `JTREG=JOBS=2;JAVA_OPTIONS=-XX:ActiveProcessorCount=2 -XX:ParallelGCThreads=2
  -XX:ConcGCThreads=1`.
- The consumers invoke the built JDK with explicit `-XX:` flags (and
  `javac -J-XX:...`), never through an environment variable.

## PID-bounded parallelism (1024-PID cgroup)

The container PID limit is 1024 and OpenJDK spawns far more processes than
`JOBS` suggests (sub-makes, javac servers, per-module JVMs, hotspot back-end
compilers, JVM GC worker threads). `--with-jobs=2`, `--with-num-cores=2`,
`JOBS=2`, `TEST_JOBS/JTREG JOBS=2` and the bounded JVM thread options above
keep the process count inside the cgroup. The `--jobs` CLI flag is still
accepted but only requests up to `BUILD_JOBS=2`; the clamp is documented in
`--help`.

## Dependency discovery

`find_jtreg()` reads `manifest.json` and prefers the declared hydrated harness
(`jtreg_harness.path`, `dependency_caches[].destination`) before falling back
to `$JTREG_HOME`/`$JT_HOME`, `$PATH`, `/workspace/cache/jtreg`,
`/workspace/input/**`, and any other `*jtreg*` directory under `/opt`,
`/usr/local`, `/usr/share`. Every candidate is version-probed the way OpenJDK's
configure does (`java -jar $JT_HOME/lib/jtreg.jar -version`, falling back to
`bin/jtreg -version`). The **highest** detected version is selected; with the
hydrated cache this resolves to `/workspace/cache/jtreg` at `7.3.1`. A too-old
system jtreg (e.g. the Ubuntu package) is reported as a missing dependency with
path, detected version and required version instead of silently breaking
configure. The boot JDK is checked separately to be in the 20.x-22.x range and
is distinct from the newly built target JDK21.0.7+6.

## Pipeline

1. `prepare()` verifies the archive sha256 and safely extracts to `/workspace/src`.
2. `bash configure --with-boot-jdk=$BOOT --with-conf-name=release
   --with-debug-level=release --with-jvm-variants=server --with-jobs=2
   --with-num-cores=2 --with-boot-jdk-jvmargs="..."
   --enable-jtreg-failure-handler=no --with-jtreg=/workspace/cache/jtreg`.
3. `make CONF=release JOBS=2 images`.
4. `build/release/images/jdk` is copied verbatim to `output/install` and
   repacked as `output/openjdk-image.tar.gz`.
5. Consumer stage outside the source tree using only the new JDK: first a
   version check that asserts the delivered image really reports `21.0.7`
   (never the boot JDK), then `javac`/`jar`/`java` on an application exercising
   collections, threads and file IO, then `javac -h` + `gcc` for a JNI shared
   library loaded by the new JVM.
6. Official tests: `make CONF=release test TEST=jdk_lang JTREG=JOBS=2;JAVA_OPTIONS=...`
   with the hydrated harness - never replaced by a custom smoke test.
7. `finish()` writes `install_manifest.json`, `install.tar.gz` and the run record.

`output/jdk_lang_inventory.json` records the test-source inventory that
`make test TEST=jdk_lang` will discover, saved before execution.
`output/jtreg_summary.json` records the parsed upstream `Test results:` line.

## Honest limitations

- `buildkit.test()`'s built-in parsers recognise pytest/gtest/ctest/unittest/
  junit/dejagnu/TAP summaries; jtreg instead prints `Test results: passed: N;
  failed: M; error: K`. When the built-in parser returns `null` the raw upstream
  log is preserved under `output/logs` and reported as target-level coverage -
  no case count is invented. The genuine jtreg summary is additionally parsed
  from that same raw log into `jtreg_summary.json`; if it reports failures or
  errors the run fails.
- Wall time depends on the PID-bounded parallelism chosen for the 1024-PID
  cgroup; it is a configuration parameter, not a measured figure.
- Only Linux x86_64 server HotSpot is produced; other JVM variants and
  cross-platform CI tiers are out of scope for the `core` profile.
- The bootstrap JDK21 in the base image is a dependency input, distinct from the
  newly built target JDK21.0.7+6 delivered under `output/install`.
