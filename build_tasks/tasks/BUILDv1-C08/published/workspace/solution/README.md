# Mesa LLVMpipe + EGL CPU software graphics stack (BUILDv1-C08, core profile)

Builds Mesa `mesa-25.1.2` from the mounted read-only source archive into a
self-contained install prefix containing:

- the `llvmpipe` gallium driver,
- EGL + GLESv2 software libraries,
- the frozen core upstream unit tests listed in `solution/main.py:TESTS`.

Vulkan / Lavapipe and Zink are deliberately out of scope for the core profile
(they live in the reference / extended profiles).

## Usage

    python3 solution/main.py doctor --input input --output output
    python3 solution/main.py run    --input input --output output --jobs 4

`doctor` prints the exact missing source / tool / dependency items and exits
with code 78 when any input is absent; it never attempts a build on a
missing-input path.

## Test discovery and selection

Before running anything the solution collects the *exact* upstream test
inventory in two stages so that the frozen selectors can be matched reliably
against whatever name the real Meson registry uses:

1. `meson introspect <build> --tests` - authoritative JSON array of every
   registered test (`name` field). This is parsed first.
2. If introspection yields nothing, the solution falls back to
   `meson test --list`.  This output is parsed for `name='...'` fields (the
   `TestSerialisation` repr emitted by some Meson releases) and, failing that,
   for bare `project:test` tokens.

Matching rules, in order:

1. exact match of the meson test name (with or without the `project:` prefix),
2. dash/underscore-normalised match (`lp_test_lerp` == `lp-test-lerp`).

Selectors that resolve are executed individually with `--print-errorlogs`
and `--num-processes 2`; selectors that do not exist in this upstream release
are recorded under `unavailable` in the emitted `test_discovery.json` so the
exact upstream revision's inventory is preserved.  If *no* frozen selector
resolves the build fails loudly rather than passing an empty suite.

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
- The frozen selector list comes from the task specification.  Where this
  specific Mesa release does not register a selector upstream, the solver
  records it in `test_discovery.json` as `unavailable` rather than inventing a
  case count or silently skipping; the tests that *do* exist upstream are all
  executed and their real meson logs are retained.
- If LLVM development packages (`llvm-config`), `libdrm`, `expat`, `zlib` or the
  core build tools are absent in the sandbox, `doctor` reports them and the
  build cannot proceed.
