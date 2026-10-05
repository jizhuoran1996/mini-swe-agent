# BUILDv1-D08 - etcd release toolset (core profile)

Builds `etcd`, `etcdctl`, `etcdutl` from the frozen source archive
(`v3.5.21`, commit `a17edfd5...`) with the upstream shell build script that
ships in that revision, runs the declared `TestStore*` MVCC selection with
`go test -json` from the module that owns the mvcc package, packages the
binaries, and consumes them outside the source tree (put/get, atomic
conditional txn, snapshot, restore into a new data directory, restart,
continue writing).

## Usage

    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run    --input /workspace/input --output /workspace/output --jobs 4

`doctor` inspects the archive and the toolchain and prints the exact source /
toolchain / dependency items that block a build. It exits `78` when anything
is missing and `0` when ready. `run` refuses to start when the archive is
absent or the checksum disagrees with the manifest.

## Upstream build entry point and MVCC package location

The frozen recipe names `scripts/build.sh`. This implementation probes the
extracted tree for `scripts/build.sh` then `build.sh`, records which one is
used in `run.json` (`build_script`), and fails loudly if neither is present.

Likewise, the MVCC selection is not bound to a hard-coded directory. After
`prepare()` the tree is scanned for the directory named `mvcc` that contains
the `TestStore*` functions, the nearest enclosing `go.mod` is treated as the
module root, and `go test -json -count=1 -timeout=10m -run <regex> ./<rel>` is
invoked from that root. `mvcc_discovery.json` records the standard path,
whether it exists, its `.go` files, every candidate `mvcc` directory, and the
one actually chosen, so a mismatch is visible instead of silent.

## Consumer transaction input

`etcdctl txn` reads a positional batch from stdin, not labelled sections:
comparisons (one per line), a blank line, the success requests, a blank line,
the failure requests, and then a final blank line. The trailing blank line is
required: `etcdctl/ctlv3/command/txn_command.go`'s `readOps` reads until it
sees an empty line and otherwise returns `io.EOF`, which the CLI reports as
`Error: EOF`. Section headers such as `success requests (get, put, del):` are
interactive prompts printed by the CLI and must not appear in batch input.

The consumer writes the genuine positional form with the terminating blank
line and asserts the success branch was taken by observing `tk == "tv"`, so a
silent fall-through to the failure branch would fail the run.

## Revision parsing for the continuation check

`etcdctl endpoint status --write-out=json` emits a JSON ARRAY of
`{"Endpoint": ..., "Status": {"header": {"revision": N}, ...}}` entries in
v3.5, so the revision lives under each entry's `Status` object rather than a
top-level `header`. `rev_of` parses that genuine shape (and the bare response
form for robustness) and still asserts the revision strictly increases after
writing `nk`, preserving the monotonicity check.

## Evidence produced under `--output`

* `logs/*.log` - stdout+stderr of every build / manifest / test / consumer command.
* `commands.json`, `tests.json` - trusted-helper records.
* `mvcc_discovery.json` - mvcc package location decision.
* `mvcc_test_summary.json` - pass/fail/skip counts parsed from the `go test -json` stream.
* `install/` - packaged binaries plus `LICENSE` / `etcd.conf.yml.sample`.
* `install.tar.gz`, `install_manifest.json` - sha256 of every delivered file.
* `consumer_report.json` - consumer steps and the revision growth after continuation.
* `run.json` - `Session.finish()` summary.

## Honest limitations

* The freeze pins `GOTOOLCHAIN=local` and `GOPROXY=off`. If the image Go is
  older than `.go-version`, or `GOMODCACHE` is not populated with the
  transitively required etcd modules, the build fails and `doctor` names the
  blocking item instead of fabricating a result.
* `go test -json` output is not among the summaries the trusted helper parser
  recognises, so target counts are computed directly from the JSON event
  stream and printed in `mvcc_test_summary.json`; any failing selected case or
  a zero-case run aborts the build.
* Snapshot restore uses the v3.5 `etcdutl snapshot restore` path. Only a
  single-member loopback cluster on freshly allocated ports is exercised; no
  Kubernetes, Docker or multi-node behaviour is claimed.
* `finish()` is reached only after a real build, a non-empty official test
  selection, and a passing consumer run.
