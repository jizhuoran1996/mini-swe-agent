#!/usr/bin/env python3
"""SciPy 1.15.3 CPU wheel build + linalg verification driver (BUILDv1-F06 core).

All interpreters/venvs live under /workspace/tools or /workspace/consumer so the
SDK output tree contains only the newly built wheel (no bootstrap Python
symlinks). The delivered wheel is copied to the output root.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from buildkit import Session  # trusted plumbing

WHEELHOUSE = Path('/opt/wheelhouse')
TOOLS_DIR = Path('/workspace/tools')
BUILD_REQS = ['meson-python', 'meson', 'ninja', 'cython', 'pythran', 'numpy',
              'pybind11', 'packaging', 'pyproject-metadata', 'beniget', 'gast',
              'ply', 'setuptools', 'wheel']
# Full frozen test dependency set (runtime v17 wheelhouse): pytest plugins and
# scientific test deps required by scipy.linalg's non-slow selection, including
# pytest-timeout, mpmath and array-api-strict.
TEST_REQS = ['pytest', 'pytest-xdist', 'pytest-timeout', 'threadpoolctl',
             'hypothesis', 'pooch', 'mpmath', 'array-api-strict']
NUMINSTALL = 'numpy==2.2.6'
TOOLS = ['gcc', 'g++', 'gfortran', 'pkg-config', 'ninja', 'python3']

CONSUMER_SRC = r'''
import numpy as np
import scipy
import scipy.linalg as sla
from scipy.linalg import _fblas, _flapack

print("scipy __file__:", scipy.__file__)
print("scipy version:", scipy.__version__)
print("numpy version:", np.__version__)
print("scipy.linalg._fblas:", _fblas.__file__)
print("scipy.linalg._flapack:", _flapack.__file__)
assert '/workspace/consumer/venv' in _fblas.__file__, _fblas.__file__
assert '/workspace/consumer/venv' in _flapack.__file__, _flapack.__file__

rng = np.random.default_rng(1234)
n = 256
M = rng.standard_normal((n, n))
A = M @ M.T + n * np.eye(n)
b = rng.standard_normal(n)
x = sla.solve(A, b, assume_a='pos')
res = np.linalg.norm(A @ x - b) / np.linalg.norm(b)
print("spd relative residual:", res)
assert res < 1e-10, res

G = rng.standard_normal((n, n)) + n * np.eye(n)
b2 = rng.standard_normal(n)
x2 = sla.solve(G, b2)
res2 = np.linalg.norm(G @ x2 - b2) / np.linalg.norm(b2)
print("general relative residual:", res2)
assert res2 < 1e-10, res2

lu = sla.lu_factor(G)
xs = sla.lu_solve(lu, b2)
print("lu_solve max diff:", float(np.max(np.abs(xs - x2))))
assert np.allclose(xs, x2, rtol=1e-10, atol=1e-12)

# Overdetermined least squares: validate against the true mathematical
# optimum (normal-equation stationarity + agreement with numpy's least-squares
# reference), not an arbitrary residual bound.
P = rng.standard_normal((64, 12))
yv = rng.standard_normal(64)
sol, _, rank, _ = sla.lstsq(P, yv)
print("lstsq rank:", rank)
assert rank == 12
# Normal equations: P.T @ (P @ sol - y) must vanish at the least-squares
# solution. Normalize by the magnitudes involved so the criterion is a genuine
# relative stationarity check, independent of problem scale.
PTP = P.T @ P
PTy = P.T @ yv
grad = P.T @ (P @ sol - yv)
grad_rel = np.linalg.norm(grad) / (np.linalg.norm(PTP) * np.linalg.norm(sol)
                                  + np.linalg.norm(PTy))
print("lstsq normal-equation relative residual:", grad_rel)
assert grad_rel < 1e-12, grad_rel
# Cross-check against numpy's own least-squares driver (independent code path
# via LAPACK gelsd/gelss); coefficients must agree and residuals must match.
ref, *_ = np.linalg.lstsq(P, yv, rcond=None)
coef_diff = np.linalg.norm(sol - ref) / max(np.linalg.norm(ref), 1e-300)
res_here = np.linalg.norm(P @ sol - yv)
res_ref = np.linalg.norm(P @ ref - yv)
print("lstsq coef rel diff vs numpy:", coef_diff, "res scipy:", res_here,
      "res numpy:", res_ref)
assert coef_diff < 1e-8, coef_diff
assert abs(res_here - res_ref) <= 1e-8 * (1.0 + res_ref), (res_here, res_ref)

from scipy.optimize import linprog
r = linprog(c=[-1.0, -2.0], A_ub=[[1.0, 1.0], [1.0, 3.0]], b_ub=[4.0, 6.0],
            bounds=[(0, None), (0, None)], method="highs")
print("linprog status:", r.status, "fun:", r.fun, "x:", r.x)
assert r.status == 0
assert abs(r.fun - (-5.0)) < 1e-8
assert np.allclose(r.x, [3.0, 1.0], atol=1e-6)
print("CONSUMER_VERIFY_OK")
'''


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _wheel_exists(name):
    if not WHEELHOUSE.is_dir():
        return False
    stem = re.escape(name.lower()).replace(r'\-', '[-_]')
    pattern = re.compile(stem + r'[-_].*\.whl$', re.I)
    for p in WHEELHOUSE.iterdir():
        if p.suffix == '.whl' and pattern.match(p.name):
            return True
    return False


def _pkgconfig(name):
    try:
        return subprocess.run(['pkg-config', '--exists', name],
                              capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


def _detect_blas():
    for blas in ['openblas', 'flexiblas', 'blas']:
        if _pkgconfig(blas):
            for lapack in ['openblas', 'flexiblas', 'lapack']:
                if _pkgconfig(lapack):
                    return blas, lapack
    raise RuntimeError('no BLAS/LAPACK pkg-config entry found')


def doctor(input_dir):
    input_dir = Path(input_dir)
    missing = []
    manifest = input_dir / 'manifest.json'
    if not manifest.is_file():
        missing.append(f'missing manifest: {manifest}')
    else:
        try:
            data = json.loads(manifest.read_text())
            source = input_dir / data['source']['filename']
            if not source.is_file():
                missing.append(f'missing source archive: {source}')
            elif _sha256(source) != data['source']['sha256']:
                missing.append(f'source archive sha256 mismatch: {source}')
        except Exception as exc:  # noqa: BLE001
            missing.append(f'manifest unreadable: {exc}')
    for tool in TOOLS:
        if shutil.which(tool) is None:
            missing.append(f'missing tool: {tool}')
    if not WHEELHOUSE.is_dir():
        missing.append(f'missing wheelhouse directory: {WHEELHOUSE}')
    else:
        for req in BUILD_REQS:
            if not _wheel_exists(req):
                missing.append(f'missing build wheel: {req}')
        for req in TEST_REQS + [NUMINSTALL.split('==')[0]]:
            if not _wheel_exists(req):
                missing.append(f'missing test wheel: {req}')
    if next((c for c in ['openblas', 'flexiblas', 'blas'] if _pkgconfig(c)), None) is None:
        missing.append('missing BLAS pkg-config (openblas/flexiblas/blas)')
    if next((c for c in ['openblas', 'flexiblas', 'lapack'] if _pkgconfig(c)), None) is None:
        missing.append('missing LAPACK pkg-config (openblas/flexiblas/lapack)')
    if missing:
        print('MISSING ITEMS:')
        for item in missing:
            print(' -', item)
        return 78
    print('READY: source, tools, BLAS/LAPACK and wheelhouse dependencies present')
    return 0


def _venv_python(session, path, name):
    session.run(['python3', '-m', 'venv', str(path)], phase='setup',
                name=name, cwd=str(TOOLS_DIR))
    return str(path / 'bin' / 'python')


def build_run(input_dir, output_dir, jobs):
    jobs = max(1, min(int(jobs), 4))
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    session = Session(input_dir, output_dir, jobs)
    src = session.prepare()

    wheel_out = session.output / 'dist'
    wheel_out.mkdir(parents=True, exist_ok=True)
    build_venv = TOOLS_DIR / 'buildvenv'
    install_venv = TOOLS_DIR / 'installvenv'
    consumer_venv = session.consumer / 'venv'
    work = session.build / 'run'
    work.mkdir(parents=True, exist_ok=True)
    tdir = session.build / 'tests'
    tdir.mkdir(parents=True, exist_ok=True)

    thread_env = {'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2',
                  'MKL_NUM_THREADS': '2', 'NUMEXPR_NUM_THREADS': '2'}
    pip_flags = ['--no-index', '--no-cache-dir', '--find-links', str(WHEELHOUSE)]

    # ---- build venv (outside the SDK output tree) ----
    bpy = _venv_python(session, build_venv, 'create_build_venv')
    session.run([bpy, '-m', 'pip', 'install'] + pip_flags +
                ['--upgrade', 'pip', 'setuptools', 'wheel'],
                phase='setup', name='build_venv_bootstrap', cwd=str(TOOLS_DIR))
    session.run([bpy, '-m', 'pip', 'install'] + pip_flags + BUILD_REQS,
                phase='setup', name='build_venv_deps', cwd=str(TOOLS_DIR))

    # ---- build the wheel (meson-python, no build isolation) ----
    blas, lapack = _detect_blas()
    config = [f'--config-settings=setup-args=-Dblas={blas}',
              f'--config-settings=setup-args=-Dlapack={lapack}',
              f'--config-settings=compile-args=-j{jobs}',
              '--config-settings=setup-args=-Dbuildtype=release']
    build_env = dict(thread_env)
    build_env['PKG_CONFIG_PATH'] = os.environ.get('PKG_CONFIG_PATH', '')
    session.run([bpy, '-m', 'pip', 'wheel', '--no-build-isolation', '--no-deps',
                 '--no-cache-dir', '--wheel-dir', str(wheel_out)] + config + [str(src)],
                cwd=str(work), phase='build', name='build_scipy_wheel',
                env=build_env, timeout=9000)
    wheels = sorted(wheel_out.glob('scipy-*.whl'))
    if not wheels:
        raise RuntimeError('scipy wheel was not produced')
    wheel = wheels[-1]
    # Deliver the newly built wheel at the SDK output root (no bootstrap venvs).
    shutil.copy2(wheel, session.output / wheel.name)

    # ---- install venv (outside the SDK output tree) ----
    ipy = _venv_python(session, install_venv, 'create_install_venv')
    session.run([ipy, '-m', 'pip', 'install'] + pip_flags +
                ['--upgrade', 'pip', 'setuptools', 'wheel'],
                phase='package', name='install_venv_bootstrap', cwd=str(TOOLS_DIR))
    session.run([ipy, '-m', 'pip', 'install'] + pip_flags + ['--no-deps', str(wheel)],
                phase='package', name='install_scipy_wheel', cwd=str(TOOLS_DIR))
    session.run([ipy, '-m', 'pip', 'install'] + pip_flags + [NUMINSTALL],
                phase='package', name='install_numpy', cwd=str(TOOLS_DIR))
    # Full frozen test dependency set; failure to resolve any is an honest abort.
    session.run([ipy, '-m', 'pip', 'install'] + pip_flags + TEST_REQS,
                phase='package', name='install_test_deps', cwd=str(TOOLS_DIR))

    # ---- official upstream test selection on the installed wheel ----
    test_env = dict(thread_env)
    test_env['SCIPY_HYPOTHESIS_PROFILE'] = 'ci'
    test_env['PYTHONDONTWRITEBYTECODE'] = '1'
    session.test('scipy.linalg_not_slow',
                 [ipy, '-m', 'pytest', '--pyargs', 'scipy.linalg', '-m', 'not slow',
                  '-q', '--no-header', '-p', 'no:cacheprovider', '-rf'],
                 cwd=str(tdir), parser='pytest_cases', env=test_env, timeout=5400)

    # ---- fresh consumer venv, outside src, uses only the new wheel ----
    cpy = _venv_python(session, consumer_venv, 'create_consumer_venv')
    session.run([cpy, '-m', 'pip', 'install'] + pip_flags +
                ['--upgrade', 'pip', 'setuptools', 'wheel'],
                phase='consumer', name='consumer_venv_bootstrap', cwd=str(session.consumer))
    session.run([cpy, '-m', 'pip', 'install'] + pip_flags + [NUMINSTALL],
                phase='consumer', name='consumer_numpy', cwd=str(session.consumer))
    session.run([cpy, '-m', 'pip', 'install'] + pip_flags + ['--no-deps', str(wheel)],
                phase='consumer', name='consumer_scipy_wheel', cwd=str(session.consumer))
    script = session.consumer / 'verify.py'
    script.write_text(CONSUMER_SRC)
    session.run([cpy, str(script)], cwd=str(session.consumer), phase='consumer',
                name='consumer_verify', env=thread_env, timeout=900)

    # ---- artifact/ABI evidence ----
    session.run([ipy, '-c',
                 'import json,scipy,scipy.linalg as s;'
                 'print(json.dumps({"version":scipy.__version__,'
                 '"path":scipy.__file__,"fblas":s._fblas.__file__,'
                 '"flapack":s._flapack.__file__}))'],
                phase='evidence', name='import_evidence', env=test_env, cwd=str(TOOLS_DIR))
    session.run([ipy, '-m', 'pip', 'show', '-f', 'scipy'], phase='evidence',
                name='pip_show_scipy', cwd=str(TOOLS_DIR))
    session.run([ipy, '-c', 'from scipy import show_config; show_config()'],
                phase='evidence', name='scipy_show_config', env=test_env, cwd=str(TOOLS_DIR))

    session.finish(features={'wheel': wheel.name, 'blas': blas, 'lapack': lapack,
                             'jobs': jobs, 'profile': 'core',
                             'numpy': NUMINSTALL,
                             'test_selection': 'scipy.linalg -m "not slow"'})


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print('usage: main.py [--help]')
        print('       main.py doctor --input DIR')
        print('       main.py run --input DIR --output DIR [--jobs N]')
        return 0
    command = argv[0]
    opts = {}
    i = 1
    while i < len(argv):
        if argv[i].startswith('--'):
            key = argv[i][2:]
            value = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith('--') else '1'
            opts[key] = value
            i += 2
        else:
            i += 1
    if command == 'doctor':
        return doctor(opts.get('input', '/workspace/input'))
    if command == 'run':
        build_run(opts.get('input', '/workspace/input'),
                  opts.get('output', '/workspace/output'),
                  int(opts.get('jobs', '4')))
        return 0
    print(f'unknown command: {command}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
