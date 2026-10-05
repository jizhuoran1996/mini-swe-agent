# BUILDv1-E05 - CORE profile

## Scope (deliberately narrower than the reference instance)
The frozen CORE contract is *not* the full `localDistro` build:

| item | reference instance | this CORE build |
| --- | --- | --- |
| target | `localDistro` archive | `:server:jar` only |
| tests | full `org.elasticsearch.index.query.*` suite | `MatchQueryBuilderTests` selection |
| consumer | running single node + HTTP queries | independent Java artifact verifier (no service) |

This driver never claims to build the whole distribution, Docker images, or any
remote/cloud plugin integration.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input            # 0 ready / 78 missing
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` lists the exact missing source / tool / dependency items. It checks for
a JDK 21 (build toolchain) and a JDK 17 (libs toolchain) under
`/usr/lib/jvm`, `/usr/lib64/jvm` and `/workspace/cache/gradle/jdks`, plus the
Gradle wrapper distribution and the offline Gradle dependency cache.

`run` does, via `buildkit.Session` (each step keeps its log + exit code):

1. `prepare()` - verify the archive SHA-256 and extract it to `/workspace/src`.
2. `./gradlew --offline --no-daemon -q javaToolchains` (diagnostic, non-fatal).
3. `./gradlew --offline --no-daemon --no-build-cache :server:jar`
4. `./gradlew --offline ... :server:test --tests org.elasticsearch.index.query.MatchQueryBuilderTests -Dtests.seed=DEADBEEF`
5. install the produced JAR under `output/install` (out-of-tree INSTALL_ROOT),
6. compile and run `solution/java/EsArtifactVerifier.java` from `/workspace/consumer`
   against the installed JAR only (JDK-only consumer, no source leakage),
7. run the *negative* consumer case against a non-JAR file and assert non-zero exit,
8. `Session.finish()` writes `install.tar.gz`, `install_manifest.json`, `tests.json`,
   `commands.json` and `run.json`.

## Java toolchain handling (Gradle 8.13)
Elasticsearch v8.17 declares two Java language levels: 21 for the build itself and
17 for several `:libs` subprojects (logging, entitlement, grok, geo). The
``-Dorg.gradle.java.installations.paths`` system property is *not* honoured for
included builds by Gradle 8.13. Instead the driver uses the **documented, supported**
mechanism:

1. It writes (merging with any pre-existing content) `GRADLE_USER_HOME/gradle.properties`:
   ```
   org.gradle.java.installations.paths=<jdk17>,<jdk21>,...
   org.gradle.java.installations.auto-download=false
   org.gradle.java.installations.auto-detect=true
   ```
2. It also passes `-Porg.gradle.java.installations.paths=...`,
   `-Porg.gradle.java.installations.auto-download=false` and
   `-Porg.gradle.java.installations.auto-detect=true` on every Gradle invocation so
   the setting propagates across included builds.

This makes the offline container resolve the languageVersion=17 ":libs" subprojects
to the locally installed OpenJDK 17 without ever reaching `api.adoptium.net`.
Upstream `languageVersion` declarations are left untouched; no Java version is
spoofed or fabricated. A `javaToolchains` diagnostic runs first and its output is
preserved in the evidence log.

## Consumer
`EsArtifactVerifier` opens the freshly built `server-*.jar` with `java.util.jar`,
asserts the query-package classes exist, checks their `CAFEBABE` bytecode magic,
reads `Implementation-Version` / `Build-Jdk-Spec` from `MANIFEST.MF`, and then - as
an independent real API consumer - loads the JAR in an isolated `URLClassLoader`
and invokes `org.elasticsearch.Version.fromString("8.17.6")` reflectively, checking
the returned value. It exits non-zero if any check fails. A negative case (a
non-JAR file) must also fail; the driver asserts `exit_code != 0` on that run.

The verifier is a library consumer - it is **not** a running Elasticsearch service.

## Honest limitations
* CORE only builds `:server:jar`; the full `localDistro` archive, REST layer tests,
  OS packages and Docker images are out of scope.
* The offline Gradle distribution and dependency cache are *bootstrap inputs*. If they
  are absent (`offline_dependencies_ready=false` in the frozen contract) the build
  fails honestly at dependency resolution - the driver never substitutes a prebuilt
  release or a cached target artifact.
* Both source-declared JDK levels (17 and 21) must already be installed locally;
  their absence is reported by `doctor` and requires no network to correct.
* No source modification, no test-expectation changes, no test skips.
* `run` will not call `Session.finish()` unless a non-empty official test selector and
  a real installed artifact exist.
