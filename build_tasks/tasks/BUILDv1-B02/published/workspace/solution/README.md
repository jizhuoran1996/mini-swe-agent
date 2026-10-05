# BUILDv1-B02 (core profile) - GCC 14.2.0 non-bootstrap C/C++ toolchain

## What this builds

From the frozen source archive `source.tar.xz` (gcc-14.2.0, sha256
`a7b39bc69cbf9e25826c5a60ab26477001f7c08d85cec04bc0e29cabed6f3cc9`) this driver:

1. verifies the archive checksum and extracts it to `/workspace/src` (top-level
directory stripped) via `buildkit.Session.prepare()`;
2. configures out-of-tree in `/workspace/build` with
   `--enable-languages=c,c++ --disable-bootstrap --disable-multilib` and
   installs to `/workspace/output/install`;
3. runs the official DejaGnu subsets `check-gcc RUNTESTFLAGS=execute.exp` and
   `check-g++ RUNTESTFLAGS=old-deja.exp` with `-j2`;
4. builds and runs independent consumers outside the source tree: a C program, a
   C++ program that throws a typed exception across a freshly built shared
   library, and a `/proc/self/maps` probe that must show the newly installed
   `libstdc++` being loaded.

This is the **core** profile: the reference profile's three-stage bootstrap is
deliberately replaced by an explicit single-pass `--disable-bootstrap` build.
The delivered toolchain is therefore *not* a bootstrapped compiler.

## Usage

    python3 solution/main.py --help
    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run --input /workspace/input \
        --output /workspace/output/install --jobs 4

`doctor` exits `0` when the checksum, tools and GMP/MPFR/MPC/zstd dependencies
are all present and `78` when any exact item is missing; it prints one `MISSING`
line per missing source file, tool or dependency. `run` performs the same check
first and refuses to start on a missing dependency (exit `78`) instead of
falling back to a prebuilt toolchain.

Every configure/build/install/test/consumer command goes through
`buildkit.Session.run`/`.test`, so argument lists, working directories, exit
codes, wall times and log digests are recorded under `--output/logs` and
summarised in `commands.json`, `tests.json`, `install_manifest.json`,
`install.tar.gz`, `consumer_report.json` and `run.json`.

## Names and prerequisites

Build parallelism is capped at 4 and test parallelism at 2. No network access,
no `sudo`, no `download_prerequisites`, no global `HOME` change is used. The
official test commands are the upstream `make check-gcc` / `make check-g++`
targets; their `.sum`/`.log` evidence is stored verbatim.

## Honest limitations

* This is the non-bootstrap core build. Generated-code differences from a
  reference three-stage bootstrap are expected and are not measured here.
* The declared scope (`execute.exp` plus the `old-deja.exp` C++ subset) is a
  small fraction of upstream's full testsuite; passing it is not evidence of
  full GCC portability.
* Only x86_64 Linux with the default 64-bit ABI is targeted; `--disable-multilib`
is intentional.
* If GMP/MPFR/MPC (or the zstd headers/library GCC 14 requires) are absent from
the image, `doctor` reports them and the build stops at exit 78. The dependency
  plan for this profile marks `offline_dependencies_ready: false`, so this is a
  real possibility in a bare environment.
* Test counts come from the upstream DejaGnu summary line
  (`# of expected passes N`). No case counts are fabricated when a parser cannot
  find a summary; the raw sums/logs are preserved instead.
* The consumer's library check asserts that the `libstdc++` mapping recorded in
  `/proc/self/maps` lives under the install prefix after the new toolchain's
  library directories are put on `LD_LIBRARY_PATH`.
