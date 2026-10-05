# BUILDv1-C01 — installable FFmpeg CPU toolkit (frozen CORE profile)

Builds FFmpeg **n7.1.1** (`db69d06eeeab4f46da15030a80d539efb4503ca8`) from the frozen
source archive into a private prefix, runs the frozen core FATE subset, and proves
the installed artefacts are usable by an independent out-of-tree consumer.

## Commands

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input          # exit 0 ready / 78 missing, no build
python3 solution/main.py run --input input --output output --jobs 4
```

`run` performs exactly:

1. `Session.prepare()` — sha256-verified extraction of `source.tar.gz` into `/workspace/src`.
2. Out-of-tree configure in `/workspace/build`:
   `--prefix=<output>/install --enable-shared --disable-static --disable-autodetect
   --disable-ffplay --disable-doc --samples=<discovered samples dir>`.
3. `make -j<jobs>` and `make install`.
4. `make fate-list` (upstream inventory saved to `fate_inventory.json`) **before** execution.
5. Frozen core FATE selectors: `fate-checkasm`, `fate-ffprobe_compact`, `fate-ffprobe_xml`
   (test parallelism capped at 2).
6. Consumer: the installed `ffmpeg` generates a 2 s / 44100 Hz sine WAV, losslessly
   transcodes it to FLAC and back; raw PCM is hashed for an exact bit-for-bit round trip;
   an out-of-tree C program compiled only against `<install>/include` + `<install>/lib`
   (rpath-pinned, `ldd` checked) re-opens and fully decodes WAV/FLAC/round-trip outputs.
7. `Session.finish()` — install manifest, `install.tar.gz`, `run.json`.

Outputs: `output/logs/*`, `output/commands.json`, `output/tests.json`,
`output/fate_inventory.json`, `output/consumer_report.json`, `output/probe_outputs.json`,
`output/install_manifest.json`, `output/install.tar.gz`, `output/deliverables/`.

## FATE environment (why `PATH`/`LD_LIBRARY_PATH` are set)

Some upstream test-input rules (e.g. the generator for `tests/data/ffprobe-test.nut`
used by `fate-ffprobe_compact` / `fate-ffprobe_xml`) invoke the built tools by plain
name and expect them to be resolvable. On a machine that happens to have a system
FFmpeg installed this silently resolves to that binary; in a clean offline image it
fails with a bare `Error 127` (GNU make's direct-exec path reports nothing but the
exit status). `run` therefore executes every FATE `make` invocation with:

* `PATH` = `<build>` : `<install>/bin` : inherited `PATH` — so the *freshly built*
  binaries are the ones found, never a prebuilt system product;
* `LD_LIBRARY_PATH` = the build-tree library directories plus `<install>/lib` — so
  the just-linked shared libraries are loaded before `make install` copies them.

The exact environment used is recorded in `run.json` under `features.fate_test_env`.

## Doctor contract

`doctor --input input` returns **78** and prints one `MISSING: ...` line per absent item
(source archive, sha256 mismatch, `cc`/`gcc`, `make`, `ar`, `ranlib`, `ld`, `python3`,
`nasm` or `yasm`). It returns **0** when everything needed for the frozen core build is
present. `run` re-runs the same check and exits 78 without building if anything is missing.

## Honest limitations

- The frozen core subset runs without external media samples: `fate-checkasm` is pure CPU
  assembly validation and the two `fate-ffprobe_*` cases synthesize their own input. If a
  real `samples`/`fate-suite` tree is mounted under `--input`, its path is passed to
  `--samples=`; if not, the configure flag still points at a declared path but **no sample
  dependent test is claimed as executed**. `fate_inventory.json` records the exact upstream
  discovery result and `tests.json` records exactly which selectors really ran.
- `nasm`/`yasm` is treated as a hard dependency because `fate-checkasm` must not silently
  degrade to an empty suite; a missing assembler is reported, not skipped.
- FATE exit codes are authoritative: if an upstream test fails, `run` aborts and the log
  tail is surfaced — results are never rewritten to skips, and expected outputs are never
  edited.
- Only the core profile is implemented (no libvpx/libx264 re-configuration); the optional
  incremental variant from the reference spec is intentionally out of scope here.
- `run.json.independent_verified` is written by the shared helper and stays `false`; the
  real independent evidence is `consumer_report.json`, `probe_outputs.json`,
  `ldd_probe_consumer` log and the hash-compared raw PCM files.
