# BUILDv1-E05 - CORE profile

## Scope (deliberately narrower than the reference instance)

| item | reference instance | this CORE build |
| --- | --- | --- |
| target | localDistro archive | the genuine :server release product JAR plus its staged dependency closure |
| tests | full org.elasticsearch.index.query.* suite | MatchQueryBuilderTests selection |
| consumer | running single node + HTTP queries | independent Java library consumers (no service) |

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
`build-tools-internal/src/main/java/org/elasticsearch/gradle/internal/
BwcSetupExtension.java` already uses (`loggedExec.args("-Dbuild.snapshot=false", ...)`).

This driver therefore passes `-Dbuild.snapshot=false` on EVERY Gradle invocation.
Nothing about the produced JAR - name, manifest, contents - is renamed, rewritten,
stripped or forged. The strict release assertion in the consumer, requiring the
manifest `Implementation-Version` to be exactly `8.17.6`, is preserved.

## Genuine target artifact location and name

`server/build.gradle` declares `base { archivesName = 'elasticsearch' }`, and the
upstream plugin
`build-tools-internal/src/main/java/org/elasticsearch/gradle/internal/
ElasticsearchJavaPlugin.java`
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

The declared release version is read offline from `version.properties`, then
`gradle/build.versions.toml`. Any trailing `-SNAPSHOT` is stripped so the expected
artifact name is the release name. If no genuine product is found the driver
fails honestly and lists every jar it actually saw, plus the Gradle-reported path.

## SDK closure staging

The earlier delivery only installed `elasticsearch-8.17.6.jar`, so a fresh
root consumer that compiled against `TermQueryBuilder` / `BoolQueryBuilder` /
`QueryBuilders` failed with `org.elasticsearch.xcontent.ToXContentObject not
found`; the classpath it was handed pointed into the source tree and the Gradle
cache, neither of which exists in a fresh network-none container.

The driver stages the genuine dependency closure into `output/install/lib`:

* `:server:esDumpConsumerClasspath` resolves the union of the real
  `runtimeClasspath` and `compileClasspath` of `:server` through the unchanged
  original Gradle graph (external modules from the offline dependency cache,
  project dependencies from the freshly built `build/distributions`);
* each entry is resolved to a real JAR. An entry that is a class directory is
  mapped to the corresponding Gradle project JAR from
  `build/distributions` (then `build/libs`) - required classes are never silently
  discarded. An entry that cannot be resolved to a real JAR is reported and the
  build fails.
* byte-identical entries are deduplicated by SHA-256; the server JAR itself is
  skipped (it already sits at the install root);
* a filename collision with differing bytes fails loudly - no dummy or
  synthesised JAR is ever created;
* bytes, manifests and original filenames are preserved byte for byte
  (`shutil.copy2`, verified again by hashing the staged copy);
* every staged file is recorded in `install/STAGED_JARS.json` with its original
  source path, byte count and SHA-256.

`install/consumer-classpath.txt` is a relocatable list (`elasticsearch-8.17.6.jar`
and `lib/<original name>`); the driver also writes an absolute variant used
in-container. A fresh container only needs to recursively collect `*.jar` under
the install root.

## Usage

    python3 solution/main.py --help
    python3 solution/main.py doctor --input input     # 0 ready / 78 missing
    python3 solution/main.py run --input input --output output --jobs 4

doctor lists the exact missing source / tool / dependency items: it checks a
JDK 21 (build toolchain; JDK 22/23 also satisfy "at least 21") and a JDK 17
(libs toolchain) under `/usr/lib/jvm`, `/usr/lib64/jvm` and
`/workspace/cache/gradle/jdks`, the presence of the plugin sources that fix the
jar location and read `build.snapshot`, plus the Gradle wrapper distribution and
the offline Gradle dependency cache.

run does, via buildkit.Session (each step keeps its log and exit code):

1. prepare() - verify the archive SHA-256 and extract it to /workspace/src.
2. `./gradlew --offline --no-daemon -Dbuild.snapshot=false -q javaToolchains`
   (diagnostic, non-fatal).
3. `./gradlew --offline --no-daemon --no-build-cache -Dbuild.snapshot=false
   :server:jar` - produces the release JAR.
4. `./gradlew --offline ... -Dbuild.snapshot=false
   -I consumer-classpath.init.gradle :server:esDumpConsumerClasspath
   :server:esReportServerJar` - resolves the genuine consumer classpath and
   reports the genuine Jar archive file. The init script only registers helper
   tasks; no project source is modified.
5. discovery of the genuine product jar.
6. `./gradlew --offline ... -Dbuild.snapshot=false :server:test --tests
   org.elasticsearch.index.query.MatchQueryBuilderTests -Dtests.seed=DEADBEEF`.
7. install the produced JAR under `output/install`, keeping its true release
   file name, and stage the resolved dependency closure under
   `output/install/lib` (deduplicated, collision-checked).
8. `EsArtifactVerifier` positive plus both unchanged negative consumer cases
   (non-JAR file, hollow JAR), run against the installed closure only.
9. `InstalledClosureVerifier` is compiled and executed against ONLY the
   delivered files: it recursively collects `*.jar` under the install root,
   loads the essential classes in an isolated `URLClassLoader`, builds a term
   query, assembles a bool query with one must and one filter clause, serialises
   it and checks both the emitted JSON and `toString()` contain `independent`
   and `exists`.
10. `Session.finish()` writes `install.tar.gz`, `install_manifest.json`,
    `tests.json`, `commands.json`, `verify.json` and `run.json`.

## JSON extraction in the consumer (fix)

`XContentBuilder` does not override `Object.toString()`, so calling
`builder.toString()` returned java object identity
(`org.elasticsearch.xcontent.XContentBuilder@723e88f9`) and the JSON branch
failed with `FAIL serialised bool query missing term value independent`.

The consumer now extracts the JSON the builder actually produced through the
ORIGINAL Elasticsearch public API
`org.elasticsearch.common.Strings.toString(XContentBuilder)`, which closes the
builder and reads its original UTF-8 output stream:

    public static String toString(XContentBuilder xContentBuilder) {
        xContentBuilder.close();
        OutputStream stream = xContentBuilder.getOutputStream();
        if (stream instanceof ByteArrayOutputStream baos) {
            return baos.toString(StandardCharsets.UTF_8);
        } else {
            return ((BytesStream) stream).bytes().utf8ToString();
        }
    }

`org.elasticsearch.common.Strings` is part of the delivered closure (the built
`:server` JAR), so no extra dependency is used. Both real serialisation branches
are preserved and asserted separately: the JSON emitted by one `bool.toXContent`
call on a fresh builder (extracted by the original API), and the independent
`BoolQueryBuilder.toString()` branch. Assertions, the delivered SDK loader check,
declared `languageVersion`s, all strict `8.17.6` checks and both negative cases
are unchanged; JSON is never fabricated and no failure is turned into a success.

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

## Consumers

`EsArtifactVerifier` opens the freshly built JAR, asserts the required
`org.elasticsearch.index.query.*` classes and `org.elasticsearch.Version` exist,
checks their CAFEBABE bytecode magic, and requires the strict release manifest
tuple `Implementation-Version == 8.17.6` (read verbatim from `META-INF/MANIFEST.MF`,
no suffix stripping, no rewriting). It then loads the JAR in an isolated
`URLClassLoader` (platform-loader parent) and invokes the real public API
`org.elasticsearch.Version.fromString` on the expected version, checks the
returned value, verifies that `MatchQueryBuilder` implements
`org.elasticsearch.index.query.QueryBuilder`, and checks that `MatchQueryBuilder`
was actually loaded from the verified artifact. It resolves the delivered
classpath file, so it consumes only files under INSTALL_ROOT.

`InstalledClosureVerifier` compiles and runs against the delivered closure only
(no source tree, no Gradle cache). It recursively discovers every delivered
`*.jar`, asserts the essential classes load from that set in isolation, then
builds and serialises the bool query described above and asserts the term field
name, the term value, the must and filter list counts and identities, and that
both the emitted JSON and `toString()` contain `independent` and `exists`.

Serialisation note: `AbstractQueryBuilder.toXContent` already performs
`builder.startObject()`, `doXContent(...)` and `builder.endObject()`, so the
consumer calls `toXContent(...)` exactly once on a fresh
`XContentFactory.jsonBuilder()` and lets the query builder emit its own complete
root object. Wrapping it in an outer `startObject()` was the bug that produced
`com.fasterxml.jackson.core.JsonGenerationException: Can not start an object,
expecting field name`.

Two negative cases must both fail:

* a non-JAR byte file (archive cannot be opened),
* a structurally valid JAR with a manifest but none of the required classes.

The verifiers are library consumers - they are not a running Elasticsearch
service.

## Honest limitations

* CORE only builds the `:server` release product JAR plus its dependency
  closure; the full localDistro archive, REST layer tests, OS packages and
  Docker images are out of scope.
* The offline Gradle distribution and dependency cache are bootstrap inputs. If
  they are absent, doctor reports it; if resolution still fails, the build fails
  honestly - the driver never substitutes a prebuilt release or a cached target
  artifact.
* Both source-declared JDK levels (17 and 21+) must be installed locally; their
  absence is reported by doctor and needs no network to correct.
* No source modification, no test-expectation changes, no test skips.
* run will not call `Session.finish()` unless a non-empty official test selector
  and a real installed artifact exist.
