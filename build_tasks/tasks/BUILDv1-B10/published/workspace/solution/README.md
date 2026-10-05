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

## Fixes retained from the previous attempt

### 1. `JAVA_TOOL_OPTIONS` / `_JAVA_OPTIONS` must not reach configure

Upstream OpenJDK configure aborts with

```
configure: You have _JAVA_OPTIONS or JAVA_TOOL_OPTIONS set. This can mess up
           the build. Please use --with-boot-jdk-jvmargs instead.
configure: error: Cannot continue
```

Every session command is launched as
`/usr/bin/env -u JAVA_TOOL_OPTIONS -u _JAVA_OPTIONS <real argv...>` so those
variables are gone regardless of what the container environment contains.
Thread bounding uses only upstream-supported knobs.

### 2. PID exhaustion: disable javac-server and drop build parallelism

The second cold build (configure `--with-jobs=2 --with-num-cores=2`, bounded
boot JVM) still failed with

```
/usr/bin/bash: fork: retry: Resource temporarily unavailable
gmake[3]: *** [lib/CompileJvm.gmk:295: ...jvmtiGetLoadedClasses.o.op_check] Error 254
```

at 4096 PIDs. jdk21u enables the javac-server by default, so each of the ~80
modules compiled its own javac daemon plus JVM worker threads, and hotspot ran
several parallel compile servers. The PID budget is exhausted by *thread and
daemon* counts, not by `JOBS` alone. The supported remedy
(`make/autoconf/build-performance.m4` exposes `--disable-javac-server`) is now
used:

```
bash configure --with-jobs=1 --with-num-cores=1 \
               --with-boot-jdk-jvmargs="-XX:ActiveProcessorCount=1 \
                 -XX:ParallelGCThreads=1 -XX:ConcGCThreads=1" \
               --disable-javac-server --enable-jtreg-failure-handler=no
make CONF=release JOBS=1 images
```

`--with-boot-jdk-jvmargs` is the supported way to bound the boot JVM; because
the makefiles thread it into every build-time `java`/`javac`/`jar` invocation,
it bounds all build JVM launches, not just the top-level one. The delivered JDK
is still a full `images` build - no modules dropped, no source edited.

`output/configure_evidence.json` records what configure actually produced
(`BOOT_JDK_JVMARGS` and `JAVAC_SERVER_ENABLED` lines from the generated
`build/release/spec.gmk`) so the environment bound is honest evidence, not a
claim.

### 3. Bounded official tests and consumers

```
make CONF=release test TEST=jdk_lang \
     JTREG="JOBS=1;JAVA_OPTIONS=-XX:ActiveProcessorCount=1 \
       -XX:ParallelGCThreads=1 -XX:ConcGCThreads=1"
```

`JOBS=`/`JAVA_OPTIONS=` inside the `JTREG` variable are the documented upstream
knobs. Every frozen `jdk_lang` test still runs - nothing is skipped or
filtered. The consumers invoke the newly built JDK directly with the same
`-XX:` flags (and `javac -J-XX:...`); no environment variable is used for them.

## Pipeline

1. `prepare()` verifies the archive sha256 and safely extracts to `/workspace/src`.
2. configure (see above), then evidence check of `build/release/spec.gmk`.
3. `make CONF=release JOBS=1 images`.
4. `build/release/images/jdk` is copied verbatim to `output/install` and
   repacked as `output/openjdk-image.tar.gz`.
5. Consumers outside the source tree using only the new JDK: a version check
   that asserts the delivered image reports `21.0.7` (ruling out the boot JDK
   false-pass), then `javac`/`jar`/`java` on an application exercising
   collections, threads and file IO, then `javac -h` + `gcc` for a JNI shared
   library loaded by the new JVM.
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
- `output/jdk_lang_inventory.json` - the test-source inventory that
  `make test TEST=jdk_lang` will discover, saved before execution.
- `output/jtreg_summary.json` - the parsed upstream `Test results:` line.

## Honest limitations

- `buildkit.test()`'s built-in parsers recognise pytest/gtest/ctest/unittest/
  junit/dejagnu/TAP/TAP summaries; jtreg instead prints
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
  target JDK21.0.7+6 delivered under `output/install`.
