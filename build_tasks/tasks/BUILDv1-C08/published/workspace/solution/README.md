# Mesa LLVMpipe + EGL CPU software graphics stack (BUILDv1-C08, core profile)

Builds Mesa `mesa-25.1.2` from the mounted read-only source archive into a
self-contained install prefix containing:

- the `llvmpipe` gallium driver,
- EGL + GLESv2 software libraries,
- the frozen core upstream unit tests: `util_tests`, `process`,
  `process_with_overrides`, `lp_test_format`, `lp_test_arit`,
  `lp_test_blend`, `lp_test_lerp`, `lp_test_conv`, `lp_test_printf`.

Vulkan / Lavapipe and Zink are deliberately out of scope for the core profile
(they live in the reference / extended profiles).

## Usage

    python3 solution/main.py doctor --input input --output output
    python3 solution/main.py run    --input input --output output --jobs 4

`doctor` prints the exact missing source / tool / dependency items and exits
with code 78 when any input is absent; it never attempts a build on a
missing-input path.

## Layout

- `/workspace/src` - extracted upstream source
- `/workspace/build` - Meson/Ninja build tree
- `/workspace/output/install` - install prefix produced by `meson install`
- `/workspace/consumer/egl_offscreen` - independent EGL consumer built and run
  outside the source tree, linked exclusively against the freshly built install
  prefix (`-L` / `LD_LIBRARY_PATH`), with the system Mesa driver path suppressed
  via `MESA_LOADER_DRIVER_OVERRIDE=llvmpipe` and `LIBGL_ALWAYS_SOFTWARE=1`.

Every build / configure / install / test / consumer command is routed through
`buildkit.Session` so command argv, exit codes and full logs are preserved
under `output/logs/` and `output/commands.json`.

## Honest limitations

- Only the CORE profile is implemented. The `swrast` Vulkan ICD (Lavapipe) is
  not built, so there is no Lavapipe consumer in this solution.
- The EGL consumer asserts `GL_RENDERER` contains `llvmpipe` and reads back a
  known clear colour. This is a functional smoke test, not a Khronos
  conformance run and not evidence about any hardware GPU driver.
- `meson test --list` is captured as the official test inventory before
  execution; the nine frozen selectors are run individually and their real
  Meson logs are retained.
- If LLVM development packages (`llvm-config`), `libdrm`, `expat`, `zlib` or the
  core build tools are absent in the sandbox, `doctor` reports them and the
  build cannot proceed.
