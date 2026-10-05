# BUILDv1-B03 — GNU binutils core (binutils/gas/ld) source build

This solution builds GNU binutils 2.44 from the supplied source archive, runs the specified official tests, installs the toolkit, and independently consumes the newly built tools from `/workspace/consumer`.

## Usage

```sh
python3 solution/main.py --help
python3 solution/main.py doctor --input /workspace/input
python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4
```

`doctor` checks the source archive checksum and required host tools (`gcc`, `make`, `sed`, `awk`, `grep`, `ar`, `ranlib`, `runtest`, `expect`, `tclsh`). It exits 78 if anything is missing and 0 when ready. `--help` never builds.

## Build and validation flow

1. `session.prepare()` verifies and extracts the locked source archive.
2. Configure with `--target=x86_64-linux-gnu --prefix=<install> --program-prefix= --disable-gdb --disable-gdbserver --disable-gold --disable-gprofng --disable-werror`.
   Empty `--program-prefix=` keeps the installed tool names as plain `as`, `ld`, `ar`, `nm`, `objcopy`, `objdump`, `readelf` (the target prefix would otherwise make them `x86_64-linux-gnu-*`). The consumer still discovers installed tools by scanning `<prefix>/bin` and also accepts an accidental `${target}-` prefix.
3. `make -j<jobs> all`.
4. Official tests recorded via the buildkit test helper:
   - `check-binutils`
   - `check-gas`
   - `ld-shared/shared.exp` (`make -C ld check RUNTESTFLAGS=ld-shared/shared.exp`)
5. `make install` into the session install prefix, and `installed_bin.json` records the real installed file paths.
6. Independent consumer under `/workspace/consumer`:
   - host `gcc -S` only produces assembly input;
   - the newly built `as` assembles objects;
   - the newly built `ar` creates an archive;
   - the newly built `ld` links with the host runtime crt files and libc;
   - `readelf`, `objdump` and `nm` inspect the result;
   - `objcopy` splits debug information, runs the stripped binary, and adds a debug link.

## Honest limitations

- This is the **core** profile: native x86_64 ELF binutils, gas and ld. GDB, gold, gprofng and simulator are disabled or not part of the delivered scope.
- Only the declared official test selectors are required and executed. Results inside DejaGnu summaries can include upstream XFAIL/UNSUPPORTED cases; those are preserved in the raw logs, not converted to passes.
- Consumer checks verify that the newly built tools are explicitly selected via their installed paths and that the produced ELF executable actually runs. They do not claim portable coverage for non-x86_64 targets or non-Linux hosts.
- No network access is used. Build tools and bootstrap Python packages are inputs, but the delivered assembler, linker, archiver, inspection and copying tools are all compiled from the supplied source release.
