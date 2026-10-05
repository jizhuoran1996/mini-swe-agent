# BUILDv1-A02 — Zstandard v1.5.7 core source build

## What this does

Builds the frozen upstream release of [Zstandard](https://github.com/facebook/zstd)
(`release_ref` v1.5.7, commit `f8745da6ff1ad1e7bab384bd1f9d742439278e99`) from the
read-only source archive at `/workspace/input`, using the project's own GNU Make
build system exactly as the upstream README documents:

1. `make -j4` in the source root (builds `libzstd` static + shared and the `zstd` CLI).
2. `make install PREFIX=/workspace/output/install` — a private prefix; nothing is
   written to system directories.
3. Official tests: `make check`, `make -C tests test-cli-tests`,
   `make -C tests test-invalidDictionaries`, `make -C tests test-legacy`,
   `make -C tests test-pool`.
4. Independent consumption **outside the source tree**: `consumer.c` (written for
   this task) is compiled against the freshly installed headers and `libzstd.so`
   and uses `ZSTD_compressStream2` / `ZSTD_decompressStream` with a shared
   dictionary. The decompressor is fed deliberately tiny 7-byte windows so frame
   boundaries and the end of frame are genuinely exercised. The CLI is driven with
   `-D <dict>` in both directions, and a 128 KiB binary fixture is round-tripped and
   byte-compared.
5. Negative cases: a corrupted compressed stream must be rejected by the delivered
   CLI, and after temporarily removing `libzstd.so` from the install prefix a fresh
   consumer must **fail** to link — proving the delivered artifact (not a system
   copy) is what is being consumed.

## Streaming control flow (fixed)

* **Compression.** `ZSTD_compressStream2()` returning `0` while a chunk is fed with
  `ZSTD_e_continue` only means "that chunk is drained" — it is not end of file. The
  loop feeds further chunks, switches to `ZSTD_e_end` for the tail, and keeps
  calling with `ZSTD_e_end` until that call returns `0` (frame fully flushed).
  Treating the first `0` as completion leaves the frame unterminated, which is
  exactly why the decompressor then reported a truncated frame.
* **Decompression.** `ZSTD_decompressStream()` returns `0` only when the frame has
  been fully decoded *and flushed*; a non-zero return is a hint for the next call.
  Input exhaustion is therefore **not** treated as completion: the loop continues
  (with an empty input window once the compressed bytes run out) so a pending final
  flush can occur, and it declares truncation only when a call makes no forward
  progress at all. A real truncation is still detected. There is no separate empty
  read loop that could reset the completion state.

## Dependencies are used as-is

The official CLI suite drives `programs/zstdless`, which pipes through the system
pager `less` (`tests/cli-tests/cltools/zstdless.sh`). The real `less` is used
verbatim. No stand-in pager is built and `PATH` is never manipulated; if `less` were
absent the run fails with an explicit dependency error and `doctor` reports it as a
missing required item (exit 78).

## Usage

```bash
python3 solution/main.py --help
python3 solution/main.py doctor --input /workspace/input
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` lists each required source file/tool/runtime dependency with its
resolution, prints a machine-readable summary, returns **78** when a required item
is missing and **0** when ready. `--help` never triggers a build.

Every build/install/test/consumer/negative command goes through
`buildkit.Session.run`/`Session.test`, so exit codes, wall time and SHA-256 of every
log are preserved under `output/logs/` and `output/commands.json`. Exit status for
the `check=False` negative cases is read back from `Session.commands[-1]["exit_code"]`
(`Session.run` returns the log path, not a process result object).

## Artifacts

| Path | Meaning |
|---|---|
| `output/install/bin/zstd` | newly built CLI |
| `output/install/lib/libzstd.{so,a}` | newly built shared/static library |
| `output/install/include/*.h` | public API headers |
| `output/install.tar.gz` | archived private install prefix |
| `output/install_manifest.json` | size + SHA-256 of every installed file |
| `output/commands.json` | every command, cwd, exit code, wall time, log hash |
| `output/tests.json` | test selectors with parsed counts and raw log paths |
| `output/source_identity.json` | pinned commit, archive/README/Makefile hashes |
| `output/official_test_inventory.json` | upstream test discovery snapshot |
| `output/dependencies.json` | resolved runtime dependency (`less`), no stand-ins |
| `output/consumer_linkage.txt` | `ldd` proof the consumer resolves the private lib |
| `output/negative_cases.json` | corrupt-input + missing-artifact results |

## Scope and honest limitations

* Frozen **core** profile only: the default `make` build, `make check`, and the four
  named regression targets. The reference-profile extension targets
  (`tests/test-zstream`, `tests/test-fuzzer`) are recorded in the inventory as
  `out_of_core_scope` and are deliberately **not** executed; no long-budget fuzzing
  and no benchmark repetition is claimed.
* `test-zstream` / `test-fuzzer` need a fixed seed and duration budget that the core
  profile does not freeze, so they are excluded rather than silently truncated.
  Nothing inside the selected targets is skipped.
* `test-cli-tests` wraps upstream shell scripts; `buildkit`'s parser cannot derive a
  numeric case count from shell output, so `parsed_count` is `null` and the raw log
  (including upstream `PASS`/`FAIL` lines) is the evidence — no count is invented.
* Optional CLI interop with `gzip`/`xz`/`lz4` and the matching library features depend
  on host headers/binaries; `doctor` reports them as optional, and upstream's own
  subtests skip accordingly when they are absent.
* No network access, no system installation, no `sudo`. `PREFIX` is fixed to the
  session-private install root and `-march=native` is never used.
* Parallelism is capped at `BUILD_JOBS <= 4`; test targets run with `-j2`
  (`TEST_JOBS <= 2`).
