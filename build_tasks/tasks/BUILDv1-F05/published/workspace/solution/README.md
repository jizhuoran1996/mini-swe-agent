# NumPy 2.2.6 source build (FROZEN CORE profile)

Builds the NumPy 2.2.6 release sdist into a wheel with meson-python, installs
it into a plain prefix, then verifies it with the upstream `numpy.linalg`
suite and independent functional / native consumers.

## Usage

```
python3 solution/main.py --help
python3 solution/main.py doctor --input input            # 78 if anything is missing, 0 when ready
python3 solution/main.py run --input input --output output --jobs 4
```

`doctor` is side-effect free: it inspects the source archive (including vendored
submodule content), system tools, `/opt/wheelhouse` dependency wheels and
BLAS/LAPACK discovery. `run` refuses to proceed when the source or declared
dependencies are absent, and never substitutes a prebuilt wheel.

## Pipeline (what `run` actually executes)

1. Extract + checksum-verify `source.tar.gz` (buildkit `prepare`).
2. Create an isolated build venv under `/workspace/build` and install `build`,
   `meson-python`, `Cython`, `ninja`, `packaging`, `pyproject-hooks` from
   `/opt/wheelhouse` (no index).
3. `python -m build --wheel --no-isolation -Csetup-args=-Dallow-noblas=false`:
   a silent fall-back to no-BLAS is forbidden, so the wheel links a real BLAS.
4. Create `/workspace/consumer/venv` with **no** system site-packages and
   install the new wheel plus `pytest`/`hypothesis` from the wheelhouse with
   `--no-index`.
5. Install the wheel into the delivered prefix `output/install` with
   `pip install --target` so it holds **only** the NumPy package - no bootstrap
   interpreter, venv or absolute interpreter symlink is ever packaged there.
6. Save the exact official test inventory (`pytest --collect-only`).
7. Run the official suite: `python -m pytest --pyargs numpy.linalg -m "not slow"`
   from the consumer venv, outside the source tree.
8. Independently consume the wheel: recorded BLAS binding, 200x200 solve
   residual, FFT round-trip error, seeded RNG reproducibility, `.npy` reload in
   a fresh process, and a C-API extension compiled against `numpy.get_include()`.

The `run.json` record carries the SHA-256 of the newly built wheel, and
`install_manifest.json` hashes every delivered package file.

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
- Logs, the command list, parsed test counts and the install manifest are
  written under the output directory by the `buildkit` session.
