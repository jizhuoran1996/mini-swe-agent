#!/usr/bin/env python3
"""SciPy 1.15.3 CPU wheel build + linalg verification driver (BUILDv1-F06 core)."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

WHEELHOUSE = Path('/opt/wheelhouse')
BUILD_REQS = ['meson-python', 'meson', 'ninja', 'cython', 'pythran', 'numpy',
              'pybind11', 'packaging', 'pyproject-metadata', 'beniget', 'gast',
              'ply', 'setuptools', 'wheel']
TEST_REQS = ['pytest', 'pytest-xdist', 'pytest-timeout', 'threadpoolctl',
             'hypothesis', 'pooch', 'mpmath', 'array-api-strict']
TOOLS = ['gcc', 'g++', 'gfortran', 'pkg-config', 'ninja', 'python3']

CONSUMER_SRC = r'''
import os, sys
import numpy as np
import scipy
import scipy.linalg as sla
from scipy.linalg import _fblas, _flapack
print("scipy __file__:", scipy.__file__)
print("scipy version:", scipy.__version__)
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
print("lu_solve diff:", float(np.max(np.abs(xs - x2))))
assert np.allclose(xs, x2, rtol=1e-10, atol=1e-12)

P = rng.standard_normal((64, 12))
y = rng.standard_normal(64)
sol, _, rank, _ = sla.lstsq(P, y)
print("lstsq rank:", rank, "residual:", float(np.linalg.norm(P @ sol - y)))
assert rank == 12
assert np.linalg.norm(P @ sol - y) < 5.0

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
    pat = re.compile(re.escape(name.lower()).replace('-', '[-_]') + r'[-_].*\.whl$', re.I)
    for p in WHEELHOUSE.iterdir():
        if p.suffix == '.whl' and pat.match(p.name):
            return True
    return False


def _pkgconfig(name):
    return subprocess.run(['pkg-config', '--exists', name],
                          capture_output=True).returncode == 0


def doctor(input_dir):
    input_dir = Path(input_dir)
    missing = []
    manifest = input_dir / 'manifest.json'
    if not manifest.is_file():
        missing.append(f'missing manifest: {manifest}')
    else:
        try:
            m = json.loads(manifest.read_text())
            src = input_dir / m['source']['filename']
            if not src.is_file():
                missing.append(f'missing source archive: {src}')
            elif _sha256(src) != m['source']['sha256']:
                missing.append(f'source archive sha256 mismatch: {src}')
        except Exception as exc:
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
        for req in TEST_REQS:
            if not _wheel_exists(req):
                missing.append(f'missing test wheel: {req}')
    blas = None
    for candidate in ['openblas', 'flexiblas', 'blas']:
        if _pkgconfig(candidate):
            blas = candidate
            break
    if blas is None:
        missing.append('missing BLAS pkg-config (openblas/flexiblas/blas)')
    lap = None
    for candidate in ['openblas', 'flexiblas', 'lapack']:
        if _pkgconfig(candidate):
            lap = candidate
            break
    if lap is None:
        missing.append('missing LAPACK pkg-config (openblas/flexiblas/lapack)')
    if missing:
        print('MISSING ITEMS:')
        for item in missing:
            print(' -', item)
        return 78
    print('READY: source, tools, BLAS/LAPACK, wheelhouse all present')
    return 0


def _detect_blas():
    for name in ['openblas', 'flexiblas', 'blas']:
        if _pkgconfig(name):
            for lap in ['openblas', 'flexiblas', 'lapack']:
                if _pkgconfig(lap):
                    return name, lap
    raise RuntimeError('no BLAS/LAPACK pkg-config found')


def build_run(input_dir, output_dir, jobs):
    sys.path.insert(0, '/opt/flash') if Path('/opt/flash').is_dir() else None
    from buildkit import Session  # noqa: E402

    jobs = max(1, min(int(jobs), 4))
    session = Session(input_dir, output_dir, jobs)
    src = session.prepare()
    build_venv = session.build / 'buildvenv'
    install_root = session.install
    consumer_venv = session.consumer / 'venv'
    wheel_out = session.output / 'dist'
    wheel_out.mkdir(parents=True, exist_ok=True)
    work = session.build / 'run'
    work.mkdir(parents=True, exist_ok=True)
    base_env = {'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2',
                'MKL_NUM_THREADS': '2', 'NUMEXPR_NUM_THREADS': '2'}

    session.run(['python3', '-m', 'venv', str(build_venv)], phase='setup',
                name='create_build_venv')
    bpy = str(build_venv / 'bin' / 'python')
    session.run([bpy, '-m', 'pip', 'install', '--no-index', '--no-cache-dir',
                 '--find-links', str(WHEELHOUSE), '--upgrade', 'pip', 'setuptools', 'wheel'],
                phase='setup', name='build_venv_bootstrap')
    session.run([bpy, '-m', 'pip', 'install', '--no-index', '--no-cache-dir',
                 '--find-links', str(WHEELHOUSE)] + BUILD_REQS,
                phase='setup', name='build_venv_deps')

    blas, lapack = _detect_blas()
    cfg = [f'--config-settings=setup-args=-Dblas={blas}',
           f'--config-settings=setup-args=-Dlapack={lapack}',
           f'--config-settings=compile-args=-j{jobs}',
           '--config-settings=setup-args=-Dbuildtype=release']
    env = dict(base_env)
    env['PKG_CONFIG_PATH'] = os.environ.get('PKG_CONFIG_PATH', '')
    session.run([bpy, '-m', 'pip', 'wheel', '--no-build-isolation', '--no-deps',
                 '--no-cache-dir', '--wheel-dir', str(wheel_out)] + cfg + [str(src)],
                cwd=str(work), phase='build', name='build_scipy_wheel', env=env,
                timeout=9000)
    wheels = sorted(wheel_out.glob('scipy-*.whl'))
    if not wheels:
        raise RuntimeError('scipy wheel not produced')
    wheel = wheels[-1]
    shutil.copy2(wheel, session.output / wheel.name)

    session.run(['python3', '-m', 'venv', str(install_root)], phase='package',
                name='create_install_venv')
    ipy = str(install_root / 'bin' / 'python')
    session.run([ipy, '-m', 'pip', 'install', '--no-index', '--no-cache-dir',
                 '--find-links', str(WHEELHOUSE), '--upgrade', 'pip', 'setuptools', 'wheel'],
                phase='package', name='install_venv_bootstrap')
    session.run([ipy, '-m', 'pip', 'install', '--no-index', '--no-cache-dir', '--no-deps',
                 str(wheel)], phase='package', name='install_scipy_wheel')
    session.run([ipy, '-m', 'pip', 'install', '--no-index', '--no-cache-dir',
                 '--find-links', str(WHEELHOUSE)] + TEST_REQS,
                phase='package', name='install_test_deps')

    test_env = dict(base_env)
    test_env['SCIPY_HYPOTHESIS_PROFILE'] = 'ci'
    test_env['PYTHONDONTWRITEBYTECODE'] = '1'
    tdir = session.build / 'tests'
    tdir.mkdir(parents=True, exist_ok=True)
    session.test('scipy.linalg_not_slow',
                 [ipy, '-m', 'pytest', '--pyargs', 'scipy.linalg', '-m', 'not slow',
                  '-q', '--no-header', '-p', 'no:cacheprovider', '-rf'],
                 cwd=str(tdir), parser='pytest_cases', env=test_env, timeout=5400)

    session.run(['python3', '-m', 'venv', str(consumer_venv)], phase='consumer',
                name='create_consumer_venv')
    cpy = str(consumer_venv / 'bin' / 'python')
    session.run([cpy, '-m', 'pip', 'install', '--no-index', '--no-cache-dir',
                 '--find-links', str(WHEELHOUSE), '--upgrade', 'pip', 'setuptools', 'wheel'],
                phase='consumer', name='consumer_venv_bootstrap')
    session.run([cpy, '-m', 'pip', 'install', '--no-index', '--no-cache-dir',
                 '--find-links', str(WHEELHOUSE), 'numpy'],
                phase='consumer', name='consumer_numpy')
    session.run([cpy, '-m', 'pip', 'install', '--no-index', '--no-cache-dir', '--no-deps',
                 str(wheel)], phase='consumer', name='consumer_scipy_wheel')
    script = session.consumer / 'verify.py'
    script.write_text(CONSUMER_SRC)
    session.run([cpy, str(script)], cwd=str(session.consumer), phase='consumer',
                name='consumer_verify', env=base_env, timeout=900)

    session.run([ipy, '-c', 'import scipy, scipy.linalg, sys; print(scipy.__version__); '
                 'print(scipy.linalg._fblas.__file__); print(sys.executable)'],
                phase='evidence', name='import_evidence', env=test_env)
    session.run([ipy, '-m', 'pip', 'show', 'scipy'], phase='evidence', name='pip_show_scipy')
    session.run([ipy, '-m', 'scipy.show_config' if False else '-c',
                 'import scipy; from scipy import show_config; show_config()'],
                phase='evidence', name='scipy_show_config', env=test_env)

    session.finish(features={'wheel': wheel.name, 'blas': blas, 'lapack': lapack,
                             'jobs': jobs})


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print('usage: main.py [--help] | doctor --input DIR | run --input DIR --output DIR [--jobs N]')
        return 0
    cmd = argv[0]
    opts = {}
    i = 1
    while i < len(argv):
        if argv[i].startswith('--'):
            key = argv[i][2:]
            val = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith('--') else '1'
            opts[key] = val
            i += 2
        else:
            i += 1
    if cmd == 'doctor':
        return doctor(opts.get('input', '/workspace/input'))
    if cmd == 'run':
        build_run(opts.get('input', '/workspace/input'),
                  opts.get('output', '/workspace/output'),
                  int(opts.get('jobs', '4')))
        return 0
    print(f'unknown command: {cmd}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
