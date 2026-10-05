# BUILDv1-E05 - CORE profile

## Scope (deliberately narrower than the reference instance)

| item | reference instance | this CORE build |
| --- | --- | --- |
| target | localDistro archive | the genuine :server release product JAR only |
| tests | full org.elasticsearch.index.query.* suite | MatchQueryBuilderTests selection |
| consumer | running single node + HTTP queries | independent Java library consumer (no service) |

This driver never claims to build the whole distribution, Docker images or any
remote/cloud plugin integration.

## Release build (why `-Dbuild.snapshot=false`)

The unchanged v8.17.6 Gradle build reads

    build-tools-internal/src/main/java/org/elasticsearch/gradle/internal/info/
    GlobalBuildInfoPlugin.java
        Util.getBooleanProperty("build.snapshot", true)

so an unmodified invocation defaults to snapshot metadata and produces
`elasticsearch-8.17.6-SNAPSHOT.jar` with `Implementation-Version: 8.17.6-SNAPSHOT`.
The upstream supported way to obtain the release artifact is
`-Dbuild.snapshot=false`, exactly as
`build-tools-internal/src/main/java/org/elasticsearch/gradle/internal/BwcSetupExtension.java`
already uses (`loggedExec.args("-Dbuild.snapshot=false", ...)`).

This driver therefore passes `-Dbuild.snapshot=false` on EVERY Gradle invocation.
Nothing about the produced JAR - name, manifest, contents - is renamed, rewritten,
stripped or forged. The strict release assertion in the consumer, requiring the
manifest `Implementation-Version` to be exactly `8.17.6`, is preserved.

## Genuine target artifact location and name

`server/build.gradle` declares `base { archivesName = 'elasticsearch' }`, and the
upstream plugin
`build-tools-internal/src/main/java/org/elasticsearch/gradle/internal/ElasticsearchJavaPlugin.java`
declares

    jarTask.getDestinationDirectory().set(new File(project.getBuildDir(), "distributions"));

so the real release product is `server/build/distributions/elasticsearch-8.17.6.jar` -
neither `server-*.jar` nor `server/build/libs/*`. Every other project jar
configured by the same plugin also lands under that project's
`build/distributions`.

Discovery is twofold and never fabricates a product:

1. **Release name first** - check `server/build/distributions/elasticsearch-8.17.6.jar`
   (and `server/build/libs/elasticsearch-8.17.6.jar`) built with `build.snapshot=false`.
2. **Authoritative archiveFile** - the helper init script registers
   `:server:esReportServerJar`, which prints the genuine Gradle Jar task
   `archiveFile`, written to `-Pes.server.jar.out=<file>` and used as a fallback.
3. **Defensive SNAPSHOT + general scan** - `-SNAPSHOT` name and any other
   `elasticsearch-*.jar` under those directories are only used as last-resort
   candidates, and every candidate must open as a zip and contain both
   `org/elasticsearch/Version.class` and
   `org/elasticsearch/index/query/MatchQueryBuilder.class`.

The declared release version is read offline from `version.properties`
(`build-tools-internal/src/main/resources/version.properties`, then the
`build-tools-internal/version.properties` fallback, then
`build-tools/src/main/resources/version.properties`), and finally from
`gradle/build.versions.toml`. Any trailing `-SNAPSHOT` is stripped so the expected
artifact name is the release name. If no genuine product is found the driver
fails honestly and lists every jar it actually saw, plus the Gradle-reported path.
The installed artifact keeps its true upstream release file name.

## Usage

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input     # 0 ready / 78 missing
    python3 solution/main.py run --input input --output output --jobs 4

doctor lists the exact missing source / tool / dependency items: it checks for a
JDK 21 (build toolchain; JDK 22/23 also satisfy "at least 21") and a JDK 17
(libs toolchain) under `/usr/lib/jvm`, `/usr/lib64/jvm` and
`/workspace/cache/gradle/jdks`, the presence of the plugin sources that fix the jar
location and read `build.snapshot`, plus the Gradle wrapper distribution and the
offline Gradle dependency cache.

run does, via buildkit.Session (each step keeps its log and exit code):

1. prepare() - verify the archive SHA-256 and extract it to /workspace/src.
2. `./gradlew --offline --no-daemon -Dbuild.snapshot=false -q javaToolchains`
   (diagnostic, non-fatal).
3. `./gradlew --offline --no-daemon --no-build-cache -Dbuild.snapshot=false
   :server:jar` - produces the release JAR.
4. `./gradlew --offline ... -Dbuild.snapshot=false
   -I consumer-classpath.init.gradle :server:esDumpConsumerClasspath
   :server:esReportServerJar` - resolves the genuine :server classpath and reports
   the genuine Jar archive file. The init script only registers helper tasks; no
   project source is modified. Stale `build/libs` entries are normalised to
   `build/distributions`, and every already-built project jar under
   `build/distributions` is added as a safety net.
5. discovery of the genuine product jar (release name first, then the
   Gradle-reported path, then the content-validated scan described above).
6. `./gradlew --offline ... -Dbuild.snapshot=false :server:test --tests
   org.elasticsearch.index.query.MatchQueryBuilderTests -Dtests.seed=DEADBEEF`.
7. install the produced JAR under `output/install` (out-of-tree INSTALL_ROOT, true
   release file name preserved).
8. compile and run `solution/java/EsArtifactVerifier.java` from
   `/workspace/consumer` against the installed JAR plus its genuine closure
   (JDK-only consumer, no source leakage).
9. two negative consumer cases against a non-JAR file and a structurally valid
   JAR that lacks the query-package classes, asserting non-zero exit each.
10. `Session.finish()` writes `install.tar.gz`, `install_manifest.json`,
    `tests.json`, `commands.json`, `verify.json` and `run.json`.

## Java toolchain handling (Gradle 8.13)

Elasticsearch v8.17 declares Java 21 for the build itself and Java 17 for several
`:libs` subprojects; the multi-release source compilation also needs later JDKs.
The `-Dorg.gradle.java.installations.paths` system property is not honoured for
included builds by Gradle 8.13. The driver uses the documented, supported
mechanism: it writes (merging with any pre-existing content)
`GRADLE_USER_HOME/gradle.properties` with the local JDK paths plus
auto-download=false / auto-detect=true, and passes the matching `-P` entries on
every Gradle invocation. Upstream `languageVersion` declarations are untouched;
no JDK is spoofed and the offline container never reaches api.adoptium.net.
JDK detection parses `javac -version`, so a JDK 22 or 23 install is reported
correctly and satisfies the `>= 21` build requirement (JDK 17 is still required
for libs).

## Consumer

EsArtifactVerifier opens the freshly built JAR, asserts the required
`org.elasticsearch.index.query.*` classes and `org.elasticsearch.Version` exist,
checks their CAFEBABE bytecode magic, and requires the strict release manifest
tuple `Implementation-Version == 8.17.6` (read verbatim from `META-INF/MANIFEST.MF`,
no suffix stripping, no rewriting). It then loads the JAR in an isolated
`URLClassLoader` (platform-loader parent, so nothing leaks from the driver
process) and invokes the real public API `org.elasticsearch.Version.fromString`
on the expected version, checks the returned value, verifies that
`MatchQueryBuilder` implements `org.elasticsearch.index.query.QueryBuilder`, and
checks that `MatchQueryBuilder` was actually loaded from the verified artifact.

The dependency closure is resolved offline by Gradle through the helper init
script (`:server:esDumpConsumerClasspath`) - the server classes need
Lucene/log4j/libs at initialisation time. If the closure cannot be resolved the
driver fails honestly rather than silently skipping the API check.

Two negative cases must both fail:

* a non-JAR byte file (archive cannot be opened),
* a structurally valid JAR with a manifest but none of the required classes.

The verifier is a library consumer - it is not a running Elasticsearch service.

## Honest limitations

* CORE only builds the `:server` release product JAR; the full localDistro
  archive, REST layer tests, OS packages and Docker images are out of scope.
* The offline Gradle distribution and dependency cache are bootstrap inputs. If
  they are absent, doctor reports it; if resolution still fails, the build fails
  honestly - the driver never substitutes a prebuilt release or a cached target
  artifact.
* Both source-declared JDK levels (17 and 21+) must be installed locally; their
  absence is reported by doctor and needs no network to correct.
* No source modification, no test-expectation changes, no test skips.
* run will not call `Session.finish()` unless a non-empty official test selector
  and a real installed artifact exist.
