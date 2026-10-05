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

`doctor` lists the exact missing source / tool / dependency items, e.g.
`gradle-wrapper-distribution` and `gradle-dependency-cache` when the offline
Gradle cache has not been prepared. Nothing is downloaded at any point.

`run` does, via `buildkit.Session` (each step keeps its log + exit code):

1. `prepare()` - verify the archive SHA-256 and extract it to `/workspace/src`.
2. `./gradlew --offline --no-daemon --no-build-cache :server:jar`
3. `./gradlew --offline ... :server:test --tests org.elasticsearch.index.query.MatchQueryBuilderTests -Dtests.seed=DEADBEEF`
4. install the produced JAR under `output/install` (out-of-tree INSTALL_ROOT),
5. compile and run `solution/java/EsArtifactVerifier.java` from `/workspace/consumer`
   against the installed JAR only (JDK-only consumer, no source leakage),
6. `Session.finish()` writes `install.tar.gz`, `install_manifest.json`, `tests.json`,
   `commands.json` and `run.json`.

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
* No source modification, no test-expectation changes, no test skips.
* `run` will not call `Session.finish()` unless a non-empty official test selector and
  a real installed artifact exist.
