# BUILDv1-D08 - etcd release toolset (core profile)

Builds `etcd`, `etcdctl`, `etcdutl` from the frozen source archive
(`v3.5.21`, commit `a17edfd5...`) using the upstream `scripts/build.sh`,
runs the declared `server/storage/mvcc` `TestStore*` selection with
`go test -json`, packages the binaries, and consumes them outside the
source tree (put/get, conditional txn, snapshot, restore to a new data
dir, restart and continue writing).

## Usage

    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run    --input /workspace/input --output /workspace/output --jobs 4

`doctor` prints the exact source/toolchain/dependency items that block a
build and exits `78` when anything is missing, `0` when ready.
`run` refuses to call `Session.finish` when the archive is missing or the
checksum does not match the manifest.

## Evidence produced under `--output`

* `logs/*.log` - every command's stdout+stderr, from the build phase to
the consumer phase.
* `commands.json`, `tests.json` - trusted helper records.
* `mvcc_test_summary.json` - parsed `go test -json` pass/fail/skip counts
  for the selected tests (raw JSON is kept in `logs/`).
* `install/` - the packaged binaries plus `LICENSE` / `etcd.conf.yml.sample`.
* `install.tar.gz`, `install_manifest.json` - sha256 of every delivered file.
* `consumer_report.json` - consumer steps and the new revision after
  continuation.
* `run.json` - `Session.finish()` summary.

## Honest limitations

* The freeze pins `GOTOOLCHAIN=local` and `GOPROXY=off`; if the image's Go
  toolchain is older than the version named in `.go-version`, or the module
  cache is not populated with the transitively required etcd modules, the
  build fails and `doctor` reports those items without fabricating a result.
* The `go test -json` output is not one of the summaries the trusted parser
  understands, so target-level counts are computed from the JSON stream and
  reported in `mvcc_test_summary.json`; if any selected case failed, `run`
  aborts rather than reporting success.
* Snapshot restore uses `etcdutl snapshot restore` (the v3.5 path). Only a
  single-member loopback cluster on freshly allocated ports is exercised;
  no Kubernetes, Docker or multi-node behaviour is claimed.
* `finish()` is only reached after a real build, a non-empty official test
  selection, and a passing consumer run.
