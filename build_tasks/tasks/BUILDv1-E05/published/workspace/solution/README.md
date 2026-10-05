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
2. `./gradlew --offline --no-daemon --no-build-cache :server:jar`
3. `./gradlew --offline ... :server:test --tests org.elasticsearch.index.query.MatchQueryBuilderTests -Dtests.seed=DEADBEEF`
4. install the produced JAR under `output/install` (out-of-tree INSTALL_ROOT),
5. compile and run `solution/java/EsArtifactVerifier.java` from `/workspace/consumer`
   against the installed JAR only (JDK-only consumer, no source leakage),
6. `Session.finish()` writes `install.tar.gz`, `install_manifest.json`, `tests.json`,
   `commands.json` and `run.json`.

## Java toolchain handling
Elasticsearch v8.17 declares two Java language levels: 21 for the build itself and
17 for several `:libs` subprojects (logging, entitlement, grok, geo). This driver
discovers every JDK on the host and passes them explicitly:

```
-Dorg.gradle.java.installations.paths=<jdk17>,<jdk21>,...
-Dorg.gradle.java.installations.auto-detect=true
-Dorg.gradle.java.installations.auto-download=false
```

so that the Frozen offline environment never attempts `api.adoptium.net`. The
upstream `languageVersion` declarations are left untouched.

## Consumer
`EsArtifactVerifier` opens the freshly built `server-*.jar` with `java.util.jar`,
asserts the query-package classes exist, checks their `CAFEBABE` bytecode magic and
reads `Implementation-Version` / `Build-Jdk-Spec` from `MANIFEST.MF`. It exits non-zero
if any check fails, so a broken artifact cannot be reported as success. It is a library
consumer - it is **not** a running Elasticsearch service.

## Honest limitations
* CORE only builds `:server:jar`; the full `localDistro` archive, REST layer tests,
  OS packages and Docker images are out of scope.
* The offline Gradle distribution and dependency cache are *bootstrap inputs*. If they
  are absent (`offline_dependencies_ready=false` in the frozen contract) the build fails
  honestly at dependency resolution - the driver never substitutes a prebuilt release
  or a cached target artifact.
* Both source-declared JDK levels (17 and 21) must already be installed locally; their
  absence is reported by `doctor` and requires no network to correct.
* No source modification, no test-expectation changes, no test skips.
* `run` will not call `Session.finish()` unless a non-empty official test selector and
  a real installed artifact exist.
