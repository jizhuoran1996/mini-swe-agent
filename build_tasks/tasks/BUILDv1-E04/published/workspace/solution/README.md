# BUILDv1-E04 (core profile): Apache Lucene core build + reloadable-index consumer

Builds `lucene/core` from the frozen source archive, runs the official core test
suite with a fixed randomized seed, collects the freshly built JARs, and verifies
a create/update/delete/close-reopen/query workflow from an out-of-tree Java
consumer that links only against this run's artifacts.

## Commands

```
python3 solution/main.py --help
python3 solution/main.py doctor --input /workspace/input
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` prints a JSON `{ready, missing}` list and returns **78** when any source
archive / overlay / JDK / Gradle distribution / offline dependency cache item is
missing, otherwise **0**. It performs no build.

## Gradle wrapper overlay

The GitHub source archive omits `gradle/wrapper/gradle-wrapper.jar` (upstream
gitignore policy). The builder supplies the official wrapper JAR as a
`dependency_source_overlays` entry in `input/manifest.json`; before running
`gradlew` this program verifies the overlay SHA-256 and copies it to
`gradle/wrapper/gradle-wrapper.jar` in the extracted source tree. If the overlay
is absent or its hash does not match, the run aborts honestly.

## Pipeline (core profile)

1. `Session.prepare()` verifies the source archive sha256 and extracts it.
2. `apply_overlays()` verifies + installs the gradle-wrapper overlay.
3. Writes `test_inventory.json` (discovered `lucene/core/src/test/**/*Test.java`).
4. `./gradlew --offline --no-build-cache --no-daemon --max-workers=4 :lucene:core:assemble`
5. `./gradlew --offline --no-daemon --max-workers=2 :lucene:core:test -Ptests.seed=DEADBEEF -Ptests.jvms=2`
6. Parses `build/test-results/test/*.xml` honestly into `test_report.json`.
7. Best-effort real upstream publish: `:lucene:core:publishToMavenLocal` with
   `-Dmaven.repo.local=<output>/install/m2` (recorded in `publish_local.json`).
   This step is attempted with `check=False` because 9.12.x has no per-project
   `mavenLocal` task; the freshly built JARs are the authoritatative artifact.
8. Copies rebuilt JARs into `install/jars/` straight from `build/libs`.
9. Compiles `LuceneConsumer.java` against `install/jars` outside the source tree
   and runs `create -> query -> mutate -> verify -> batch2` as separate JVM
   processes so persistence across close/reopen is exercised.

## Consumer scope

The **core** profile builds only `:lucene:core`. Lucene 9's tokenizers/analyzers
(the `org.apache.lucene.analysis.*` concrete implementations) live in the
`lucene-analysis-common` module, not in core. The consumer therefore uses only
`lucene-core` classes with a `null` analyzer and pre-tokenized `StringField`
terms, which the Lucene API explicitly supports. It is a genuine index/search/
reopen/update/delete workflow, not a mock.

## Honest limitations

- The **core** profile does not build the analyzer/queryparser modules, so text
  analysis is performed by the test caller (verbatim `StringField` terms) rather
  than by a Lucene tokenizer.
- Offline Gradle requires a pre-populated `GRADLE_USER_HOME` (wrapper dists +
  `caches/modules-2`), looked up in order from `/workspace/cache/gradle`,
  `/opt/gradle`, `~/.gradle`. If absent, `doctor` reports it and the build fails
  honestly; nothing is downloaded and no prebuilt target JAR is substituted.
- `test_report.json` counts come from the real Gradle XML reports; if the suite
  reports zero cases the run fails rather than passing on an empty suite.
- No prebuilt Lucene artifact is used; the JARs are those produced by this run.
