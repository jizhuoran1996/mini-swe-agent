# BUILDv1-B10 - OpenJDK 21 server image source build

Builds the frozen OpenJDK 21.0.7+6 source release
(`jdk21u` commit `4215779271750e6409bdfbd6d94d16002bd9b6a7`,
sha256 `1888a5b967240efc83d3786667af1b3b8f75de5646c96c39bfccc9e331d9e5e9`)
into a distributable server JDK image, runs the official `jdk_lang` jtreg group
and consumes the freshly built JDK outside the source tree.

## Commands

```
# Dependency report only - never triggers a build.
python3 solution/main.py doctor --input input --output output

# Full pipeline: configure -> make images -> package -> consumer -> jtreg -> finish
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` exits `0` when every required source / tool / dependency item is
present and `78` (EX_CONFIG) otherwise. It prints the exact missing items as
JSON. `run` performs the same gate first and exits `78` before touching the
build tree if anything is missing, so a failed gate never leaves a partial
image behind.

## What is executed (all through buildkit.Session)

1. `prepare()` verifies the archive sha256 and safely extracts it into
   `/workspace/src` (top-level directory stripped).
2. `bash configure --with-boot-jdk=... --with-conf-name=release
   --with-debug-level=release --with-jvm-variants=server
   --enable-jtreg-failure-handler=no --with-jtreg=...`
3. `make CONF=release JOBS=4 images`
4. The resulting `build/release/images/jdk` tree is copied verbatim to
   `output/install` and repacked as `output/openjdk-image.tar.gz`.
5. Consumer stage (outside the source tree, only the new JDK):
   `java -version`, `javac`+`jar`+`java` on an application with collections,
   threads and file IO, then `javac -h` + `gcc` for a JNI shared library
   loaded by the new JVM with `-Djava.library.path`.
6. Official tests: `make CONF=release test TEST=jdk_lang JTREG=JOBS=2`.
7. `finish()` writes `install_manifest.json`, `install.tar.gz` and the run
   record.

The exact `jdk_lang` source inventory under `test/jdk/java/lang` is saved to
`output/jdk_lang_inventory.json` before execution.

## Honest limitations

- The frozen profile currently advertises `offline_dependencies_ready: false`.
  In this container `jtreg` is not present under any searched location, so
  `doctor` and `run` correctly report a missing dependency and exit `78`
  instead of silently skipping the `jdk_lang` group. The builder is expected to
  preload `jtreg` (and a boot JDK) and retry; no test count is ever invented.
- `buildkit.test()`'s built-in parsers understand pytest/gtest/ctest/unittest/
  junit/dejagnu/TAP summaries. jtreg emits `Test results: passed: N; failed: M`
  instead, so when the parser returns `null` the raw upstream log is preserved
  in `output/logs` and reported as target-level coverage rather than converted
  into a fabricated case count.
- Building the full image needs roughly 20-40 minutes wall time at `JOBS=4`.
  The declared deadline is a configuration parameter, not a measured figure.
- Only Linux x86_64 server HotSpot is produced; other JVM variants and
  cross-platform CI tiers are out of scope for the `core` profile.
