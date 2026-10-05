# BUILDv1-E01 (core profile) - Apache Kafka clients JAR

Frozen source: apache/kafka @ f745dfdcee2b9851204ddbbcd423626ab87294bc (release 3.9.1),
sha256 9aa86aa4b739a5b93e9d3fddda15721edfc700ce3f96364f91de120cdca8f87e.

Frozen scope (core): build **only** the clients JAR, run the official
`clients:test --tests RequestResponseTest` selection, and consume the freshly
installed JAR from an independent serialization consumer compiled outside the
source tree. No broker, no `releaseTarGz`, no Docker, no multi-host tests.

## Usage

    python3 solution/main.py --help                 # no build, no host access
    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

`doctor` exits 0 when every required item is present and 78 while anything is
missing; it lists each item and how to provide it. `run` re-uses the same check
and refuses to build (exit 78) instead of faking progress.

## What `run` does

1. checksum-verify the frozen archive and extract it into `/workspace/src`
   (`buildkit.Session.prepare`, unsafe members rejected).
2. `gradle --offline --no-daemon --no-build-cache --max-workers=4 -PmaxParallelForks=2
   -PmaxScalacThreads=4 -PskipSigning=true -PcommitId=<commit> :clients:jar`
3. `... :clients:test --tests RequestResponseTest -PmaxTestRetries=0`
4. parse the real Gradle JUnit XML under `clients/build/test-results/test/` into
   `official_tests_inventory.json` (per-case suite/test/status, failures, skips).
5. install the built `kafka-clients-3.9.1.jar` into `<output>/install/lib` and
   reject any jar that predates this session.
6. copy `solution/consumer/KafkaProtocolRoundTrip.java` to `/workspace/consumer`,
   compile and run it with a classpath that contains **only** the installed jar
   (plus auxiliary runtime jars found in the offline cache).

Evidence written to the output directory: `doctor.json`, `commands.json`,
`tests.json`, `official_tests_inventory.json`, `build_manifest.json`,
`consumer_evidence.json`, `install_manifest.json`, `install.tar.gz`, `run.json`,
and one log per executed command under `logs/`.

## Offline prerequisites reported by `doctor`

* the frozen source archive with the exact sha256;
* JDK >= 11 including `javac` (17/21 recommended);
* a Gradle binary of the same major version as `gradle-wrapper.properties`
  (searched via `KAFKA_GRADLE_HOME`, `GRADLE_HOME`, `/opt/gradle*`, `PATH`, and a
  pre-populated `$GRADLE_USER_HOME/wrapper/dists`);
* a pre-populated Gradle dependency cache with `modules-2`, exposed through
  `GRADLE_RO_DEP_CACHE` (no network is available during the build);
* a writable `/workspace`.

## Honest limitations

* The Gradle *wrapper* cannot download its distribution offline. When only an
  installed Gradle of the matching major version exists, that binary is used and
  the substitution is recorded in `build_manifest.json`; otherwise `doctor`
  reports the missing distribution and returns 78.
* Gradle's console output does not print `Tests run:`, so `tests.json` keeps
  `parsed_count: null` and the authoritative numbers are the counts parsed from
  the upstream JUnit XML files.
* The independent consumer verifies real wire round trips of generated protocol
  messages (`ApiVersionsRequestData` v0/v3/v4), a truncated-payload negative case
  and `StringSerializer`/`StringDeserializer`. It does not exercise a broker.
