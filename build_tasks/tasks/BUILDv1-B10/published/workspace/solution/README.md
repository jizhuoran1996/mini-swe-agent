# BUILDv1-B10 - OpenJDK 21 server image source build

Builds the frozen OpenJDK 21.0.7+6 source release
(`jdk21u` commit `4215779271750e6409bdfbd6d94d16002bd9b6a7`,
sha256 `1888a5b967240efc83d3786667af1b3b8f75de5646c96c39bfccc9e331d9e5e9`)
into a distributable server JDK image, runs the official `jdk_lang` jtreg
group with the SHA-verified `jtreg 7.3.1+1` harness at
`/workspace/cache/jtreg`, and consumes the freshly built JDK outside the
source tree.

## Commands

```
# Dependency report only - never triggers a build.
python3 solution/main.py doctor --input input --output output

# Full pipeline: configure -> make images -> package -> consumer -> jtreg -> finish
python3 solution/main.py run --input input --output output --jobs 2
```

`doctor` exits `0` when every required source/tool/dependency is present and
`78` (EX_CONFIG) otherwise, printing the exact missing items as JSON. `run`
performs the same gate first and exits `78` before touching the build tree if
anything is missing, so a failed gate never leaves a partial image behind.

## PID-bounded parallelism (fix for the 1024-PID cgroup)

The container PID limit is 1024. OpenJDK's build spawns many more processes
than `JOBS` suggests: shell sub-makes, `javac` servers, per-module batch JVMs,
hotspot back-end compilers, and JVM GC/compiler worker threads. The previous
run hit the hard PID wall (`fork: Resource temporarily unavailable`,
`pthread_create failed (EAGAIN)`). All of the following are now fixed rather
than configuration-tunable, because they are the parameters the PID budget
depends on:

- `configure` uses `--with-jobs=2`
  and `--with-boot-jdk-jvmargs="-XX:ActiveProcessorCount=2 -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1"`.
- `make` uses `JOBS=2` for `images`.
- Every JVM spawned through the session (configure probes, make, jtreg, the
  built JDK's own `java`/`javac`, and our consumer runs) inherits
  `JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=2 -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1`.
- jtreg is launched as `make CONF=release test TEST=jdk_lang JTREG=JOBS=2`.

The `--jobs` CLI flag is still accepted but only ever requests up to
`BUILD_JOBS=2`; requesting more is a no-op (documented in `--help`).

## Dependency discovery

`find_jtreg()` reads `manifest.json` and prefers the declared hydrated harness
(`jtreg_harness.path`, `dependency_caches[].destination`) before falling back
to `$JTREG_HOME`/`$JT_HOME`, `$PATH`, `/workspace/cache/jtreg`,
`/workspace/input/**`, and any other `*jtreg*` directory under `/opt`,
`/usr/local`, `/usr/share`. Every candidate is version-probed the way
OpenJDK's `configure` does:

```
java -jar $JT_HOME/lib/jtreg.jar -version
```

with `bin/jtreg -version` as a fallback. The **highest** detected version is
selected; with the hydrated cache present this resolves to
`/workspace/cache/jtreg` at `7.3.1`. The Ubuntu `/usr/share/jtreg` package is
older than jdk21u's required 7.3.1 and is reported as a missing dependency
(path + detected version + required version) rather than silently breaking
`configure`. The boot JDK is separately checked to be in the 20.x-22.x range
and is independent from the newly built target JDK21.0.7+6 (the base image's
`/usr/lib/jvm/java-21-openjdk-amd64`).

## Pipeline

1. `prepare()` verifies the archive sha256 and safely extracts it into
   `/workspace/src`.
2. `bash configure --with-boot-jdk=$BOOT --with-conf-name=release
   --with-debug-level=release --with-jvm-variants=server --with-jobs=2
   --with-boot-jdk-jvmargs="..." --enable-jtreg-failure-handler=no
   --with-jtreg=/workspace/cache/jtreg`.
3. `make CONF=release JOBS=2 images`.
4. `build/release/images/jdk` is copied verbatim to `output/install` and
   repacked as `output/openjdk-image.tar.gz`.
5. Consumer stage (outside the source tree, only the new JDK): `java -version`,
   `javac`+`jar`+`java` on an application with collections, threads and file
   IO, then `javac -h` + `gcc` for a JNI shared library loaded by the new JVM.
6. Official tests: `make CONF=release test TEST=jdk_lang JTREG=JOBS=2` using
   the hydrated harness - never replaced with a custom smoke.
7. `finish()` writes `install_manifest.json`, `install.tar.gz` and the run
   record.

`output/jdk_lang_inventory.json` records the exact test-source inventory that
`make test TEST=jdk_lang` will discover, saved before execution.

## Honest limitations

- `buildkit.test()`'s built-in parsers understand pytest/gtest/ctest/unittest/
  junit/dejagnu/TAP summaries; jtreg emits `Test results: passed: N;
  failed: M` instead, so when the parser returns `null` the raw upstream log is
  preserved in `output/logs` and reported as target-level coverage rather than
  a fabricated case count. Empty-discovery detection still triggers on jtreg's
  own "No tests were found" wording.
- Wall time depends heavily on the PID-bounded parallelism chosen for the
  1024-PID cgroup; it is a configuration parameter, not a measured figure.
- Only Linux x86_64 server HotSpot is produced; other JVM variants and
  cross-platform CI tiers are out of scope for the `core` profile.
- The bootstrap JDK21 in the base image is a dependency input, distinct from
  the newly built target JDK21.0.7+6 delivered under `output/install`.
