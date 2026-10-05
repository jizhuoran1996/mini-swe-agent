# BUILDv1-E03 (core profile) — Apache Flink flink-core

Builds, tests, installs and independently consumes the `flink-core` reactor of
Apache Flink `release-1.20.1` (commit `cb1e7b55`), using the frozen source archive.

## Commands

```
python3 solution/main.py doctor --input input
python3 solution/main.py run --input input --output output --jobs 4
```

* `doctor` performs genuine, offline checks (archive checksum, required source
  entries, JDK >= 17 with `javac`, and a populated local Maven repository with the
  compiler/surefire/jar/resources plugins and `org/apache/flink` artifacts).
  It prints a JSON report listing every missing source/tool/dependency item and
  returns `78` when anything is missing, `0` when ready.
* `run` re-runs the doctor checks first; on success it builds and tests the module
  (`-pl flink-core -am`, `-Djdk17 -Pjava17-target`), copies the produced reactor
  JARs into `output/install/lib`, compiles `FlinkCoreSerializationConsumer` outside
  the source tree against only those installed JARs, and runs both a positive
  roundtrip and a negative truncated-read assertion.
* `--help` works without any build or environment access.

## Output layout

```
output/
  commands.json        every executed argv with exit code and log hash
  tests.json           official test selector evidence (parsed upstream summary)
  modules.json         module + goals + installed jar list
  logs/                raw stdout/stderr per command
  install/lib/*.jar    newly built artifacts
  install_manifest.json / install.tar.gz
  run.json
```

## Honest limitations

* The build is strictly offline (`mvnw -o`). If the local Maven repository is not
  populated for this commit, `doctor` reports the exact missing plugin/org.apache.flink
  artifacts and the program exits `78` instead of fabricating a build.
* Test counts come from the real surefire output. If the upstream summary cannot be
  parsed, the raw log is preserved and no case count is invented.
* Scope is the core profile only: no flink-dist closure, connectors, Python API or
  cluster end-to-end tests are built or claimed.
* The consumer exercises `DataOutputSerializer`/`DataInputDeserializer` from the
  freshly installed JARs; it is not a substitute for the full distribution job.
