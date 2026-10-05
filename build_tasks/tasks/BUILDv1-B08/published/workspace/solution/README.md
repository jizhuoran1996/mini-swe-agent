# BUILDv1-B08 (core) — Go toolchain from source

Builds Go 1.24.4 from the pinned upstream source archive, installs the
complete tree into `output/install`, runs the frozen official package
tests, and exercises the installed toolchain from an out-of-tree consumer
module.

## Usage

```
python3 solution/main.py doctor --input input          # exits 0 or 78
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` prints, one line per item, the presence of the source archive
(sha256 verified against `manifest.json`), a bootstrap Go tree that meets
the upstream minimum, and the C build tools. It returns 0 when ready and
78 when any required item is missing, without performing a build.

`--help` is available without any build step.

## Bootstrap requirement

Upstream go1.24.x requires a bootstrap toolchain of **go1.22.6 or later**.
The builder selects, in order:

1. `--bootstrap <path>` if given,
2. the `GOROOT_BOOTSTRAP` environment variable,
3. `/opt/bootstrap/go` (supplied by the official runtime, expected go1.23.10),
4. common system locations.

Every candidate is version-checked with `<root>/bin/go version`; a
candidate whose version is `< 1.22.6` (for example the distro `go1.22.2`)
is explicitly rejected and recorded in `toolchain_report.json`. The built
**go1.24.4** target is copied to `output/install` and never the bootstrap.

## Frozen core scope

* `linux/amd64`, `CGO_ENABLED=0`.
* Official test packages: `bytes`, `strings`, `encoding/json`,
  `compress/gzip`.
* Deliverable: complete pure Go native toolchain.

## Pipeline

1. `Session.prepare()` verifies the source archive sha256 and extracts it
   safely into `/workspace/src`.
2. Resolves and records a bootstrap Go toolchain (>= 1.22.6).
3. Runs `bash ./make.bash` inside `src/` with `GOROOT_BOOTSTRAP`,
   `GOTOOLCHAIN=local`, `GOPROXY=off`, `GOMAXPROCS=4`, and a dedicated
   `GOCACHE`.
4. Confirms the produced `bin/go version` matches `go1.24.4`, then copies
   the whole tree to `output/install` (VCS metadata excluded).
5. Runs `install/bin/go test -count=1 -json` for the frozen packages and
   parses the JSON action stream into `output/official_test_evidence.json`
   (package pass/test-pass counts, no cached results allowed).
6. Independent consumer verification: a small Go module under
   `/workspace/consumer/mod` is tested (`go test ./...`), built, and run
   using only the installed toolchain.

## Evidence

* `output/logs/*.log` — raw stdout/stderr per command.
* `output/commands.json`, `output/tests.json` — buildkit command/test log.
* `output/official_test_evidence.json` — per-package and per-test counts
  parsed from the official `go test -json` stream.
* `output/toolchain_report.json` — pin, bootstrap identity and rejected
  candidates, delivered GOROOT.
* `output/install_manifest.json`, `output/install.tar.gz` — delivered tree.
* `output/run.json` — session summary.

## Honest limitations

* Only the frozen core test packages are executed; this is not the full
  upstream `run.bash` platform matrix.
* `CGO_ENABLED=0`, so no cgo consumer or cgo support is delivered by this
  core profile; the reference/extended profiles would add those.
* Test success is scoped to this Linux/amd64 host and the pinned revision;
  it is not a claim about all platforms Go supports.
* No network is used; `GOPROXY=off` and `GOTOOLCHAIN=local` guarantee the
  consumer cannot silently fetch another compiler or module.
