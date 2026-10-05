# BUILDv1-B10 - OpenJDK 21 server image source build

Builds the frozen OpenJDK 21.0.7+6 source release
(`jdk21u` commit `4215779271750e6409bdfbd6d94d16002bd9b6a7`,
sha256 `1888a5b967240efc83d3786667af1b3b8f75de5646c96c39bfccc9e331d9e5e9`)
into a distributable server JDK image, runs the official `jdk_lang` jtreg
group with the SHA-verified jtreg 7.3.1+1 harness, and consumes the freshly
built JDK outside the source tree.

## Commands

```
# Dependency report only - never triggers a build.
python3 solution/main.py doctor --input input --output output

# Full pipeline: configure -> make images -> package -> consumer -> jtreg -> finish
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` exits `0` when every required source/tool/dependency is present and
`78` (EX_CONFIG) otherwise, printing the exact missing items as JSON. `run`
performs the same gate first and exits `78` before touching the build tree if
anything is missing, so a failed gate never leaves a partial image behind.

## Dependency discovery

`find_jtreg()` reads `manifest.json` and prefers the declared hydrated harness
(`jtreg_harness.path`, `dependency_caches[].destination`) before falling back
to `$JTREG_HOME`/`$JT_HOME`, `$PATH`, `/workspace/cache/jtreg`,
`/workspace/input/**`, and any other `*jtreg*` directory under `/opt`,
`/usr/local`, `/usr/share`. The version of each candidate is probed exactly the
way OpenJDK's `configure` does:

```
java -jar $JT_HOME/lib/jtreg.jar -version
```

with `bin/jtreg -version` as a fallback. The **highest** detected version is
selected. With the hydrated cache present this resolves to
`/workspace/cache/jtreg` at version `7.3.1`, so `configure --with-jtreg` and
`make ... TEST=jdk_lang JTREG=JOBS=2` both use the real harness. The Ubuntu
`/usr/share/jtreg` package is much older than jdk21u's required 7.3.1 and is
reported as a **missing dependency** (path + detected version + required
version) rather than silently breaking `configure`, and the too-old harness is
never passed to `configure`. The boot JDK is checked to be in the 20.x-22.x
range required by jdk21u and is independent from the newly built target
JDK21.0.7+6.

## Pipeline

1. `prepare()` verifies the archive sha256 and safely extracts it into
   `/workspace/src` (top-level directory stripped).
2. `bash configure --with-boot-jdk=$BOOT --with-conf-name=release
   --with-debug-level=release --with-jvm-variants=server
   --enable-jtreg-failure-handler=no --with-jtreg=/workspace/cache/jtreg`.
3. `make CONF=release JOBS=4 images`.
4. `build/release/images/jdk` is copied verbatim to `output/install` and
   repacked as `output/openjdk-image.tar.gz`.
5. Consumer stage (outside the source tree, only the new JDK):
   `java -version`, `javac`+`jar`+`java` on an application with collections,
   threads and file IO, then `javac -h` + `gcc` for a JNI shared library
   loaded by the new JVM.
6. Official tests:
   `make CONF=release test TEST=jdk_lang JTREG=JOBS=2` using the hydrated
   harness.
7. `finish()` writes `install_manifest.json`, `install.tar.gz` and the run
   record.

`output/jdk_lang_inventory.json` records the exact test-source inventory that
`make test TEST=jdk_lang` will discover, saved before execution.

## Honest limitations

- `buildkit.test()`'s built-in parsers understand pytest/gtest/ctest/unittest/
  junit/dejagnu/TAP summaries; jtreg emits `Test results: passed: N;
  failed: M` instead, so when the parser returns `null` the raw upstream log is
  preserved in `output/logs` and reported as target-level coverage rather
  than a fabricated case count. Empty-discovery detection triggers on jtreg's
  own "No tests were found" wording.
- Building the full image needs roughly 20-40 minutes wall time at `JOBS=4`.
  The declared deadline is a configuration parameter, not a measured figure.
- Only Linux x86_64 server HotSpot is produced; other JVM variants and
  cross-platform CI tiers are out of scope for the `core` profile.
- The bootstrap JDK21 in the base image is a dependency input, distinct from
  the newly built target JDK21.0.7+6 delivered under `output/install`.
