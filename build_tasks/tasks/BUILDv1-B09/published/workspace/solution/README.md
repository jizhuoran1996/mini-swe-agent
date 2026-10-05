# BUILDv1-B09 (frozen CORE profile)

Bootstrap a **stage1** Rust toolchain (`rustc` + target `std` + `rustdoc`) from the
frozen upstream Rust 1.87.0 source archive, install it, run the frozen
const-generics UI directory with the newly built compiler, and consume the
installed toolchain from outside the source tree.

## Usage

```sh
python3 solution/main.py doctor --input /workspace/input   # 0 if ready, 78 if not
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
python3 solution/main.py --help                             # never builds
```

## What `run` does

1. `Session.prepare()` verifies the archive SHA-256 and extracts it into `/workspace/src`.
2. Rejects the build if required submodule/dependency payload is absent
   (`vendor/`, `.cargo/config.toml`, `library/backtrace`, `library/stdarch`, and
   `src/llvm-project/llvm` or a system `llvm-config`).
3. Verifies the frozen `.cargo/config.toml` declares `[source.crates-io]`
   vendored-source replacement and that the subprocess environment sets
   `CARGO_NET_OFFLINE=true` (checked against the *exact* env dict handed to
   `Session.run`).
4. Writes `bootstrap.toml`. The field set is validated against the frozen
   1.87.0 `[build]` schema: `build`, `host`, `target`, `extended`, `docs`,
   `jobs`, and — for stage0 selection — `rustc` and `cargo`. **`build.rustdoc`
   is intentionally NOT emitted**: Rust 1.87.0's `[build]` section has no
   `rustdoc` key (stage0 rustdoc is discovered from the stage0 toolchain / PATH),
   and emitting it causes the fatal `Failed to parse 'bootstrap.toml': unknown
   field rustdoc` error. `change-id` is omitted because 1.87.0 accepts only an
   integer for it. Also set: `[install]` prefix/sysconfdir, `[llvm]
   download-ci-llvm = false`, `targets = "X86"`, `link-jobs = 1`, `[rust]
   download-rustc = false`, `incremental = false`, `debuginfo-level* = 0`.
5. `x.py build --stage 1 -j <jobs>` — real stage1 `rustc`, target `std`, `rustdoc`.
   LLVM is compiled from the frozen source submodule when present.
6. `x.py install --stage 1` into `--output/install`. Only the newly built stage1
   compiler is installed; the stage0 bootstrap compiler at `/opt/bootstrap/rust`
   is never copied into the delivered install tree.
7. `x.py test --stage 1 tests/ui/const-generics --force-rerun` (2 test threads,
   no `--bless`). Full compiletest log preserved; counts parsed from real
   `test result:` lines; non-empty passing coverage mandatory.
8. Consumer verification, cwd `/workspace/consumer` (outside `src`):
   - Provenance: `rustc -vV` must report a `release:` starting with `1.87.0`
     and host `x86_64-unknown-linux-gnu`; the installed binary must *not* be
     byte-identical to the stage0 bootstrap rustc. We deliberately do **not**
     grep for a literal `stage1` token — official channel strings are just
     `dev`/`beta`/etc.
   - `rustc --print sysroot` must resolve inside the delivered install prefix,
     and `<sysroot>/lib/rustlib/x86_64-unknown-linux-gnu/lib` must contain
     `libstd*` (the target std from *this* source build).
   - Positive fixture `good.rs` (generics, `HashMap`, threads/`mpsc`, file IO).
   - Negative fixture `bad.rs` must be rejected with `E0505`.
   - Cross-crate ABI: `calc.rs` → `libcalc.rlib`, `use_calc.rs` links it and runs.
   - `rustdoc lib_doc.rs` emits HTML under `doc_out/consumer_doc/index.html`;
     expected items are asserted.
9. `Session.finish()` writes the install manifest, `install.tar.gz`, `run.json`.

## Doctor semantics

`doctor` inspects the **frozen archive/context only** and never treats an
un-extracted `/workspace/src` as a missing source item. It returns **78** and
lists the exact missing item when any of these is absent or invalid:

- `manifest.json`, or its declared `source` entry,
- the source archive (missing, wrong size, or SHA-256 mismatch),
- any required builder tool (`bash`, `gcc`, `g++`, `cmake`, `ninja`, `python3`,
  `pkg-config`, `make`, `ld`, `ar`, `tar`, `cargo`, `rustdoc`, `rustc`),
- a stage0 bootstrap token missing from `/opt/bootstrap/rust/bin` — runtime v10
  provides rustc/cargo/std 1.86.0 there; `B09_STAGE0_ROOT` can override.

It returns **0** only when all of the above are present. Submodule content
(`library/backtrace`, `library/stdarch`, `src/llvm-project/llvm` or a system
`llvm-config`) and vendored-crate checks run at build time, *after* extraction.

## Honest limitations

- **Stage0 is a dependency input.** `/opt/bootstrap/rust` (rustc/cargo/std
  1.86.0) compiles stage1 but is never the delivered product; the provenance
  check rejects an install that is byte-identical to stage0.
- **LLVM mode.** When `src/llvm-project/llvm` is present it is compiled from
  source (`llvm.download-ci-llvm = false`); a system `llvm-config` is then
  ignored. Only if the source submodule is absent is a system `llvm-config`
  used, purely as a build dependency. No LLVM or rustc binary is ever
  downloaded.
- **Offline / vendored Cargo.** `CARGO_NET_OFFLINE=true` is set for every step
  and the frozen source's vendored-source replacement is verified before build.
- **Scope.** Core profile: stage1, `extended = false`, `docs = false`, no Cargo
  deliverable, X86 target only. Stage1 ABI and usability differ from stage2.
- **Test coverage** is exactly `tests/ui/const-generics`, executed on the newly
  built stage1 compiler. It is not the full upstream CI matrix.
- **Resource scale.** A full stage1 build with source LLVM is very large and may
  exceed a three-hour budget on slow hosts. Timeouts are explicit and real
  command failures surface as failures, never as skips.
