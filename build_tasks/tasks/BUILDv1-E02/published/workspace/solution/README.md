# BUILDv1-E02 — Spark core build, DAGSchedulerSuite and local RDD consumer

## Profile

This is the **core** profile of BUILDv1-E02, which deliberately differs from
the reference SQL/Hive distribution scope:

* build the official `core` Maven module **plus its reactor dependencies**
  (`-pl core -am`),
* run the official `org.apache.spark.scheduler.DAGSchedulerSuite`,
* install the produced JARs into `/workspace/output/install`,
* compile and run an independent **local RDD** consumer (Java) from outside the
  source tree, using only the newly built JARs.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input /workspace/input        # exit 78 if not ready, 0 if ready
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` lists every exact missing source / tool / offline-dependency item.
`run` refuses to proceed (exit 78) when `doctor` reports missing prerequisites.

## What `run` does

1. `Session.prepare()` — verifies the archive SHA-256 and extracts it safely.
2. `configure` — records `mvn -v` and `java -version`.
3. Records the official test inventory (`test_inventory.json`) **before**
   execution by counting `test("...")` declarations in the frozen suite source.
4. `build` — `mvn -o -B -ntp -pl core -am -T <jobs> -DskipTests install` with
   checkstyle / rat / scalastyle / javadoc skips.
5. Copies every non-test/-sources/-javadoc JAR from `**/target/*.jar` into
   `/workspace/output/install/jars`.
6. `official_test` — `mvn -o -B -ntp -pl core -Dtest=none
   -DwildcardSuites=org.apache.spark.scheduler.DAGSchedulerSuite test`.
   The raw log and an extracted ScalaTest summary are preserved.
7. `package` — `dependency:build-classpath` resolves the runtime classpath
   from the local Maven repository.
8. `consumer` — `javac` + `java` of `solution/consumer/RddConsumer.java`
   outside the source tree, with the installed JARs first on the classpath.
   It asserts sum=55, even count=5, max=10, partitions=2 and prints
   `RDD_CONSUMER_OK`. A negative run with only the classes dir on the classpath
   must fail (proves the consumer truly loads the new artifacts).
9. `Session.finish()` writes `install_manifest.json`, `install.tar.gz` and
   `run.json`.

All build / configure / install / test / consumer commands go through
`Session.run` or `Session.test`, so exit codes, wall times and log digests are
preserved under `/workspace/output/logs`.

## Resource limits honoured

* build parallelism: `-T <jobs>` clamped to at most 4 (`Session` also clamps).
* test parallelism: ScalaTest runs single-threaded inside one Maven fork
  (<= 2).
* no `-march=native`, no unrestricted link concurrency, no fuzzing.
* fully offline: every Maven invocation uses `-o` and an explicit
  `-Dmaven.repo.local`.

## Limitations (honest)

* The core profile is **not** a full Spark distribution: there is no
  `spark-submit`, no SQL/Hive, no `make-distribution.sh` tarball. That is the
  reference profile, not this one.
* The build requires a pre-populated offline Maven repository containing the
  Spark reactor dependency closure (Scala, Hadoop client, Log4j2, ScalaTest,
  Maven plugins). When that is absent, `doctor` reports the exact missing
  artifact groups and exits 78; the harness deliberately does **not** fake a
  build or substitute a pre-installed Spark.
* ScalaTest output is not matched by `buildkit`'s auto parser, so
  `tests.json` may carry `parsed_count: null`. The raw log plus
  `scalatest_report.json` are preserved instead; no case counts are invented.
* `spark.local.dir` is redirected through `TMPDIR` to `/workspace/consumer/tmp`
  rather than through a full distribution's `spark-env.sh`.
* Native (JNI) acceleration may be absent in the reactor build; local mode
  falls back to the JVM implementations automatically. No test is skipped for
  this.
