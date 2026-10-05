# BUILDv1-E02 — Spark core build, DAGSchedulerSuite and delivered RDD consumer

## Profile (frozen core contract)

This is the **core** profile of BUILDv1-E02, deliberately different from the
reference SQL/Hive distribution scope:

* build the official `core` Maven module **plus its reactor dependencies**
  (`-pl core -am`),
* run the unmodified official `org.apache.spark.scheduler.DAGSchedulerSuite`,
* install the freshly built JARs **and the genuine external runtime dependency
  closure** under `/workspace/output/install`,
* compile and run an independent **local RDD** consumer from outside the source
  tree, using only the delivered files.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input /workspace/input
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` lists every exact missing source / tool / offline-dependency item and
returns 78 when not ready, 0 when ready. `run` refuses to proceed (exit 78)
when `doctor` reports missing prerequisites. `--help` never triggers a build.

## Offline Maven repository

The offline dependency cache is resolved in this order:

1. `MAVEN_REPOSITORY` (the task environment points this at the hydrated cache)
2. `MAVEN_REPO_LOCAL` / `MAVEN_LOCAL_REPO`
3. `/workspace/cache/maven`
4. `/workspace/input/m2`, `$HOME/.m2/repository`, `/opt/m2`, `/workspace/m2`

The same resolved path is used by **every** Maven invocation, both through
`-Dmaven.repo.local=<repo>` and by exporting `MAVEN_REPOSITORY` /
`MAVEN_REPO_LOCAL` to the child process. No Maven command runs without an
explicit offline repository, and every Maven command uses `-o`.

## What `run` does

1. `Session.prepare()` verifies the archive SHA-256 and extracts it safely.
2. `configure` records `mvn -v` and `java -version`.
3. Records the official test inventory **before** execution by counting
   `test("...")` declarations in the frozen suite source, and parses Spark's
   original Java 17 module flags from the unmodified
   `launcher/src/main/java/org/apache/spark/launcher/JavaModuleOptions.java`.
4. `build`: `mvn -o -B -ntp -Dmaven.repo.local=<repo> -pl core -am -T <jobs>
   -DskipTests install` (checkstyle/rat/scalastyle/javadoc skips only).
5. `package`: `dependency:build-classpath -DincludeScope=runtime` resolves the
   genuine runtime dependency closure from the same local repository.
6. **Delivery staging**: every reactor JAR from `**/target/*.jar` (excluding
   `original-`, `-tests`, `-sources`, `-javadoc`) and every external runtime
   dependency JAR is copied into `install/jars/` under its original name.
   Exact bytes are deduplicated by SHA-256; two distinct files sharing a
   filename but not their bytes are a hard error (`jar_collisions.json`). A
   relocatable `install/classpath.txt` lists the delivered files.
7. `test`: the real selector `-DwildcardSuites=org.apache.spark.scheduler.DAGSchedulerSuite`
   runs. The raw log is preserved and a ScalaTest summary is extracted into
   `scalatest_report.json`.
8. `consumer`: `RddConsumer.java` is compiled and launched **with only the
   delivered JARs** on the classpath (no source tree, no Maven cache paths).
   Spark's original Java 17 module flags (including
   `--add-opens=java.base/sun.nio.ch=ALL-UNNAMED`) are supplied explicitly, so
   the `StorageUtils$ -> sun.nio.ch.DirectBuffer` `IllegalAccessError` cannot
   recur and no `spark-submit` injection is required. The consumer asserts the
   small arithmetic (sum 55, evens 5, max 10, 2 partitions), a 1..100 -> x2 ->
   10100 transform over 4 partitions, and a real shuffle group-by stage.
9. **Negative case**: the identical launch with the delivered JARs removed
   must fail with `NoClassDefFoundError` / `ClassNotFoundException` (nonzero
   exit), proving the consumer truly loads the delivered artifacts.
10. `Session.finish()` writes `install_manifest.json`, `install.tar.gz` and
    `run.json`.

All build / configure / install / test / consumer commands go through
`Session.run` or `Session.test`; exit codes, wall times and log digests are
preserved under `/workspace/output/logs`.

## What a fresh root consumer needs

`install.tar.gz` is self-contained: it carries the freshly compiled Spark core
reactor JARs plus the genuine external runtime dependency closure under
original names/bytes. A consumer outside this repository with Java 17, no
network and no Maven cache can therefore compile a real `JavaSparkContext` job
against `install/jars/*` and run it, provided Spark's original Java 17 module
flags are passed to `java` (as this harness does).

## Resource limits honoured

* build parallelism: `-T <jobs>` clamped to at most 4.
* test parallelism: one Maven fork, fewer than 2 concurrent test processes.
* no `-march=native`, no unrestricted link concurrency, no fuzzing.
* fully offline: `-o` plus explicit `-Dmaven.repo.local` on every Maven command.

## Limitations (honest)

* The core profile is **not** a full Spark distribution: there is no
  `spark-submit`, no SQL/Hive, no `make-distribution.sh` tarball. That is the
  reference profile, not this one.
* The build requires the pre-populated offline Maven repository containing the
  Spark reactor dependency closure (Scala, Hadoop client, Log4j2, ScalaTest,
  Maven plugins). When absent, `doctor` reports the exact missing artifact
  groups and exits 78; the harness never fakes a build and never substitutes a
  pre-installed Spark.
* ScalaTest output is not matched by `buildkit`'s auto parser, so `tests.json`
  may carry `parsed_count: null`. The raw log plus `scalatest_report.json` are
  preserved instead; no case counts are invented.
* `spark.local.dir` is redirected through `TMPDIR` / `SPARK_LOCAL_DIRS` to
  `/workspace/consumer/tmp`, not through a distribution's `spark-env.sh`.
* The negative case demonstrates a missing-JAR failure; it is not a suite and
  contributes no official case counts.
