# SciPy 1.15.3 CPU wheel build (BUILDv1-F06, core profile)

Builds the official SciPy 1.15.3 sdist into a Linux CPU wheel using
meson-python with `--no-build-isolation` (all backend deps installed from
`/opt/wheelhouse`), installs the resulting wheel into a fresh prefix,
runs the upstream `scipy.linalg` non-slow test selection on the installed
wheel, then installs the same wheel into an independent consumer venv and
validates real numerical semantics (SPD/general solves, `lu_solve`,
`lstsq`, and a `linprog` LP with known optimum).

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

`doctor` exits 78 when any source, tool, BLAS/LAPACK, or required
wheelhouse dependency is missing, and 0 when everything is ready.

## Scope (core)

* Full Linux CPU wheel (C, C++, Fortran, Cython, Pythran extension modules).
* Official upstream test selection: `pytest --pyargs scipy.linalg -m "not slow"`.
* Independent consumer under `/workspace/consumer/venv` (no system site
  packages) importing the newly built wheel and asserting numeric residuals.

## Out of scope / honest limitations

* The reference profile's `scipy.optimize` official suite is not part of the
  core test set; `linprog` is only exercised by the consumer functional check.
* No `SCIPY_XSLOW`, no `slow` marker collection, no extended modules
  (`sparse`, `signal`).
* Wheel identity (timestamps/checksums) is not byte-reproducible; only the
  release ref, version, and native module provenance are asserted.
* `doctor` checks pkg-config BLAS presence but does not verify BLAS numerical
  correctness; that is covered by the consumer's residual checks.
