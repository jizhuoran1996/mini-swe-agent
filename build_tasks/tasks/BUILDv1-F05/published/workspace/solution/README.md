# NumPy 2.2.6 source build (FROZEN CORE profile)

Builds the NumPy 2.2.6 release sdist into a wheel with meson-python, installs
it into an isolated prefix, then verifies it with the upstream `numpy.linalg`
test suite and independent functional / native consumers.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input        # exit 78 if anything is missing, 0 when ready
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` performs no side effects: it only inspects the source archive, the
system tools, `/opt/wheelhouse` dependency wheels and the BLAS/LAPACK discovery.
`run` refuses to proceed when the extracted source or the declared dependencies
are absent, and never substitutes a prebuilt wheel.

## Pipeline (what `run` actually executes)

1. Extract + checksum-verify `source.tar.gz` (buildkit `prepare`).
2. Create an isolated build venv and install `build`, `meson-python`, `Cython`,
   `ninja`, `packaging`, `pyproject-hooks` from `/opt/wheelhouse` (no index).
3. `python -m build --wheel --no-isolation -Csetup-args=-Dallow-noblas=false` —
   a silent fall-back to no-BLAS is forbidden, so the wheel links a real BLAS.
4. Install the new wheel (no deps, no index) into an isolated install prefix.
5. Create `/workspace/consumer/venv` with **no** system site-packages, install
   the new wheel plus `pytest`/`hypothesis` from the wheelhouse with `--no-index`.
6. Save the exact official test inventory (`pytest --collect-only`).
7. Run the official suite: `python -m pytest --pyargs numpy.linalg -m "not slow"`.
8. Independently consume the wheel: BLAS record, 200x200 solve residual, FFT
   round-trip error, seeded RNG reproducibility, `.npy` reload in a fresh
   process, and a C-API extension compiled against `numpy.get_include()`.

## Honest limitations

- BLAS/LAPACK flavour, threading and CPU baseline are whatever the environment
  auto-detects (LP64, `allow-noblas=false`); ILP64 and cross-compilation are not
  exercised. The exact BLAS binding is recorded from `numpy.show_config`.
- Only the CORE scope is validated: the full wheel plus the non-slow
  `numpy.linalg` suite. The broader `--pyargs numpy -m "not slow"` reference
  suite, F2PY and platform wheels are out of scope for this profile.
- `doctor` returns 78 (not 0) whenever the source archive, a required tool, a
  wheelhouse dependency wheel, a vendored submodule directory or BLAS is
  missing; the build then fails honestly instead of degrading features.
- Build/test logs, the command list, parsed test counts and the install manifest
  are written under the output directory by the `buildkit` session.
