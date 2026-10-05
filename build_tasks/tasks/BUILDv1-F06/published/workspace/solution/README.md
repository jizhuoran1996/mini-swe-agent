# SciPy 1.15.3 CPU wheel build (BUILDv1-F06, core profile)

Builds the official SciPy 1.15.3 sdist into a Linux CPU wheel with
meson-python and `--no-build-isolation` (backend dependencies installed from
`/opt/wheelhouse`), installs the produced wheel into a private prefix, runs the
upstream `scipy.linalg` non-slow test selection against that installed wheel,
and then installs the same wheel into an independent consumer venv that checks
real numerical semantics (SPD/general solves, `lu_solve`, `lstsq`, and a
`linprog` LP with a known optimum).

## Artifact layout

The SDK output tree contains only the newly built artifact plus evidence:

    <output>/scipy-1.15.3-*.whl   # delivered target wheel
    <output>/dist/scipy-*.whl     # meson-python build output
    <output>/logs/*.log           # preserved subprocess logs
    <output>/{commands,tests,run}.json

All interpreters, virtualenvs and bootstrap tooling live outside the SDK output
tree (their `bin/python` symlinks never enter `output/install`):

    /workspace/tools/buildvenv      # backend/toolchain venv
    /workspace/tools/installvenv    # install + official-test prefix
    /workspace/consumer/venv        # independent consumer venv

No bootstrap Python interpreter is packaged as a target SDK artifact; the
secure artifact filter therefore accepts the output tree.

## Commands

    python3 solution/main.py --help
    python3 solution/main.py doctor --input /workspace/input
    python3 solution/main.py run --input /workspace/input --output /workspace/output --jobs 4

`doctor` exits 78 when any source, tool, BLAS/LAPACK or required wheelhouse
dependency is missing, and 0 when everything is ready.

## Dependencies (runtime v17)

* Build backend: meson-python, meson, ninja, Cython, Pythran, pybind11, NumPy.
* Test dependencies (full frozen set): pytest, pytest-xdist, pytest-timeout,
  threadpoolctl, hypothesis, pooch, mpmath, array-api-strict.
* NumPy pinned to 2.2.6 (within SciPy 1.15.3's declared `>=1.23.5,<2.5` range).

An absent required dependency aborts the run honestly via the Session helper;
the timeout plugin and array fixtures are not silently dropped.

## Scope (core)

* Full Linux CPU wheel (C, C++, Fortran, Cython, Pythran native modules).
* Official upstream selection: `pytest --pyargs scipy.linalg -m "not slow"`.
* Independent consumer under `/workspace/consumer/venv` (no system site
  packages) importing only the newly built wheel and asserting residuals and a
  known optimization optimum.

## Out of scope / honest limitations

* The reference profile's `scipy.optimize` official suite is not part of the core
  test selection; `linprog` is only exercised by the consumer functional check.
* No `SCIPY_XSLOW` and no `slow` marker collection.
* Extended modules (`sparse`, `signal`) are not built or tested here.
* Wheel byte-identity is not asserted; the source release ref, reported version,
  native module provenance, and numeric residuals are.
* `doctor` verifies pkg-config BLAS/LAPACK presence, not numerical correctness;
  the consumer residual/target checks cover that.
