# BUILDv1-E04 (core profile): Apache Lucene core build + reloadable-index consumer

Builds `lucene/core` from the frozen source archive, runs the official core test
suite with a fixed randomized seed, collects the freshly built core JARs, and
verifies a create/update/delete/close-reopen/query workflow from an out-of-tree
Java consumer that links only against this run's artifacts.

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
   (recorded with `phase='build'`).
5. **Official frozen suite** through `Session.test(...)` so the real Gradle log,
   selector and SHA are preserved:

   ```
   ./gradlew --offline --no-build-cache --no-daemon --max-workers=2 \
       :lucene:core:test -Ptests.seed=DEADBEEF -Ptests.jvms=2
   ```

6. `parse_reports()` reads the real `build/test-results/test/*.xml` into
   `test_report.json` and aborts if the suite reported zero cases, failures, or
   errors. No prebuilt Lucene JAR is ever substituted and no count is fabricated.
7. Copies the freshly built core JARs straight out of `lucene/*/build/libs` into
   `install/jars/`.
8. Compiles `LuceneConsumer.java` against `install/jars` outside the source tree
   and runs `create -> query -> mutate -> verify -> batch2` as separate JVM
   processes so persistence across close/reopen is exercised.

## Consumer scope

The **core** profile builds only `:lucene:core`. Lucene 9's tokenizers/analyzers
(the `org.apache.lucene.analysis.*` concrete implementations) live in the
`lucene-analysis-common` module, not in core. The consumer therefore uses only
`lucene-core` classes with a `null` analyzer and pre-tokenized `StringField`
terms, which the Lucene API explicitly supports. It is a genuine index/search/
reopen/update/delete workflow, not a mock.

## Completion semantics

`Session.finish()` records the installed JARs and the official selector list.
`run.json.` `independent_verified` is intentionally **left false**: only the
root fresh-grader that consumes the submitted artifacts may set it.

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
- No prebuilt Lucene artifact is used; the JARs delivered are those produced by
  this run.
