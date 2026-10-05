# LLVM/Clang core-profile source build

Usage:

    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

`doctor` verifies the mounted source archive, its manifest checksum, and required bootstrap tools. It prints exact missing source/tool/dependency items and exits 78 when not ready, otherwise 0. `--help` is available without a build.

`run` extracts the frozen source release, configures LLVM/Clang for X86 with clang only (no lld), builds with at most 4 jobs and a fixed single parallel link job, records test inventory, runs `check-llvm-unit` and `check-clang` with 2 test jobs, installs the toolchain, packages `install/` as `toolchain.tar.gz`, then builds and runs independent C and C++ consumers outside the source tree using the newly installed `clang`, `clang++`, `llvm-ar`, and `llvm-readelf`. Consumer assertions cover static-library linking, C++ exceptions, deterministic stdout, and X86_64 ELF output.

## ELF architecture verification

The consumer ELF check now parses the raw ELF header directly (`e_machine` field at offset 18, little-endian) and requires `e_machine == 62` (EM_X86_64), `EI_CLASS == ELFCLASS64` and `EI_DATA == little-endian`. As secondary evidence the `llvm-readelf -h` human-readable rendering is preserved and matched against the documented GNU/LLVM spelling `Advanced Micro Devices X86-64` (accepting `EM_X86_64` too), together with confirmation of ELF64 and little-endian. This removes the earlier false negative caused by expecting the literal token `EM_X86_64` in readelf output.

## Honest limitations

- This is the frozen **core** scope: X86 target plus clang, deliberately **without lld**. `check-lld` is not part of this profile.
- Bootstrap host tools (`gcc`, `g++`, `cmake`, `ninja`, system linker) and host C/C++ runtime libraries are dependency inputs. The delivered target products are the newly built LLVM/Clang install tree and its installed binaries/libraries.
- The official test evidence is preserved as real lit/ninja logs. Where the trusted helper's generic parser returns no numeric case count, the detailed lit output is retained instead of inventing counts.
- The build is large. In the constrained offline container the full LLVM+Clang configure/build/test/install may exceed the wall-clock or workspace budget; the driver does not downgrade required features or convert failures into skips.
- No network access is used. Missing bootstrap dependencies are reported honestly and must be prepared by the builder outside this program.
