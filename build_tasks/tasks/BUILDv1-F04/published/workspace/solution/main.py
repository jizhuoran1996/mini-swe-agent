#!/usr/bin/env python3
"""BUILDv1-F04 (core): build scikit-learn wheels from source and verify.

Subcommands:
  run     --input DIR --output DIR [--jobs N]   full build/install/verify
  doctor  --input DIR                           readiness probe (0 ok / 78 missing)

Core scope: full native wheel + official sklearn.neighbors.tests.test_kd_tree.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import buildkit


WHEELHOUSE = Path('/opt/wheelhouse')

BUILD_REQ = ['numpy', 'scipy', 'cython', 'meson-python', 'ninja']
BUILD_TOOLS = ['build', 'wheel', 'setuptools', 'packaging', 'pyproject-hooks']
RUNTIME_REQ = ['numpy', 'scipy', 'joblib', 'threadpoolctl']
TEST_REQ = ['pytest', 'hypothesis']
TOOLS = ('gcc', 'g++', 'ninja', 'make', 'python3')


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _dist(name):
    return re.sub(r'[-_]+', '-', name.lower())


def _wheelhouse_wheels(name):
    if not WHEELHOUSE.is_dir():
        return []
    wanted = _dist(name.split('>')[0].split('=')[0].split('<')[0])
    found = []
    for entry in WHEELHOUSE.iterdir():
        if entry.suffix != '.whl':
            continue
        dist = _dist(entry.name.split('-')[0])
        if dist == wanted:
            found.append(entry)
    return found


def doctor(input_dir):
    missing = []
    inp = Path(input_dir)
    manifest_path = inp / 'manifest.json'
    if not manifest_path.is_file():
        missing.append('source manifest not found: %s' % manifest_path)
    else:
        manifest = json.loads(manifest_path.read_text())
        src = manifest.get('source', {})
        archive = inp / src.get('filename', 'source.tar.gz')
        if not archive.is_file():
            missing.append('source archive not found: %s' % archive)
        else:
            try:
                actual = buildkit.digest(archive)
            except OSError as exc:
                actual = 'unreadable (%s)' % exc
            expected = src.get('sha256')
            if expected and actual != expected:
                missing.append('source archive checksum mismatch: %s' % archive)
    for tool in TOOLS:
        if shutil.which(tool) is None:
            missing.append('required tool not on PATH: %s' % tool)
    py = shutil.which('python3')
    if py:
        probe = subprocess.run(
            [py, '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'],
            capture_output=True, text=True)
        try:
            major, minor = (int(x) for x in probe.stdout.strip().split('.'))
        except Exception:
            major, minor = 0, 0
        if (major, minor) < (3, 10):
            missing.append('python3 must be >= 3.10 (found %s)' % probe.stdout.strip())
    if not WHEELHOUSE.is_dir():
        missing.append('offline wheelhouse not found: %s' % WHEELHOUSE)
    else:
        for dep in sorted(set(BUILD_REQ + BUILD_TOOLS + RUNTIME_REQ + TEST_REQ)):
            if not _wheelhouse_wheels(dep):
                missing.append('wheelhouse dependency not found: %s' % dep)
    return missing


# --------------------------------------------------------------------------- #
# consumer verification programs (executed from the freshly built wheel)
# --------------------------------------------------------------------------- #
CONSUMER_FIT = r'''
import pickle, sys
from pathlib import Path
import numpy as np
import sklearn
import sklearn.neighbors._kd_tree as kdt

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
print("sklearn.__file__ =", sklearn.__file__)
print("kd_tree.__file__ =", kdt.__file__)
assert "/workspace/src" not in sklearn.__file__, "sklearn imported from source tree"
assert ("site-packages" in sklearn.__file__) or ("dist-packages" in sklearn.__file__)

rng = np.random.RandomState(0)
X = rng.randn(400, 6)
Q = rng.randn(12, 6)
tree = kdt.KDTree(X)
d, i = tree.query(Q, k=5)
brute = np.sqrt(((X[None, :, :] - Q[:, None, :]) ** 2).sum(-1))
brute_i = np.argsort(brute, axis=1)[:, :5]
brute_d = np.take_along_axis(brute, brute_i, 1)
assert np.allclose(d, brute_d, atol=1e-9), "KDTree distances differ from brute force"
assert np.allclose(np.take_along_axis(brute, i, 1), d, atol=1e-9), "KDTree indices inconsistent"
print("KDTree vs brute force: OK", d.shape)

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

rng = np.random.RandomState(7)
Xp = rng.randn(300, 6)
yp = (Xp[:, 0] + 0.7 * Xp[:, 1] - 0.5 * Xp[:, 2] > 0.1).astype(int)
Xt = rng.randn(50, 6)
pipe = Pipeline([("scaler", StandardScaler()),
                 ("clf", LogisticRegression(max_iter=1000))]).fit(Xp, yp)
pred = pipe.predict(Xt)
prob = pipe.predict_proba(Xt)
assert pred.shape == (50,) and prob.shape == (50, 2)
print("Pipeline train accuracy = %.3f" % pipe.score(Xp, yp))
with (out / "pipeline.pkl").open("wb") as fh:
    pickle.dump(pipe, fh)
np.save(out / "Xtest.npy", Xt)
np.save(out / "expected_pred.npy", pred)
np.save(out / "expected_prob.npy", prob)
print("saved pipeline and expectations to", out)
'''

CONSUMER_RELOAD = r'''
import pickle, sys
from pathlib import Path
import numpy as np
import sklearn

d = Path(sys.argv[1])
with (d / "pipeline.pkl").open("rb") as fh:
    pipe = pickle.load(fh)
X = np.load(d / "Xtest.npy")
exp_p = np.load(d / "expected_pred.npy")
exp_pr = np.load(d / "expected_prob.npy")
got_p = pipe.predict(X)
got_pr = pipe.predict_proba(X)
assert (got_p == exp_p).all(), "reloaded predictions differ"
assert np.allclose(got_pr, exp_pr, atol=1e-12), "reloaded probabilities differ"
print("reload OK; sklearn", sklearn.__version__)
'''


# --------------------------------------------------------------------------- #
# build pipeline
# --------------------------------------------------------------------------- #
def run(args):
    session = buildkit.Session(args.input, args.output, jobs=args.jobs)
    session.prepare()

    scripts = session.consumer / 'scripts'
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / 'consumer_fit.py').write_text(CONSUMER_FIT)
    (scripts / 'consumer_reload.py').write_text(CONSUMER_RELOAD)

    pip_env = {'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PIP_NO_CACHE_DIR': '1'}

    # 1) build venv (no isolation; local backend stack from wheelhouse)
    build_venv = session.build / 'build-venv'
    session.run([sys.executable, '-m', 'venv', str(build_venv)],
                phase='configure', name='create_build_venv')
    bpy = build_venv / 'bin' / 'python'
    session.run([str(bpy), '-m', 'pip', 'install', '--no-index',
                 '--find-links', str(WHEELHOUSE), *(BUILD_REQ + BUILD_TOOLS)],
                phase='configure', name='install_build_deps', env=pip_env)

    # 2) compile the wheel from source (meson-python -> ninja)
    artifact_dir = session.output / 'artifacts'
    artifact_dir.mkdir(parents=True, exist_ok=True)
    build_env = dict(pip_env)
    build_env.update({
        'NINJAFLAGS': '-j%d' % session.jobs,
        'CMAKE_BUILD_PARALLEL_LEVEL': str(session.jobs),
        'MAKEFLAGS': '-j%d' % session.jobs,
        'PYTHONDONTWRITEBYTECODE': '1',
    })
    session.run([str(bpy), '-m', 'build', '--wheel', '--no-isolation',
                 '--outdir', str(artifact_dir),
                 '--config-setting=compile-args=-j%d' % session.jobs,
                 str(session.src)],
                phase='build', name='meson_compile_wheel',
                env=build_env, timeout=7200)
    wheels = sorted(artifact_dir.glob('scikit_learn-*.whl'))
    if not wheels:
        raise RuntimeError('wheelhouse build produced no wheel in %s' % artifact_dir)
    wheel = wheels[0]

    # 3) install into $INSTALL_ROOT (isolated venv, drops source-tree loader)
    install_venv = session.install / 'venv'
    session.run([sys.executable, '-m', 'venv', str(install_venv)],
                phase='install', name='create_install_venv')
    ipy = install_venv / 'bin' / 'python'
    session.run([str(ipy), '-m', 'pip', 'install', '--no-index', '--find-links',
                 str(WHEELHOUSE), *(RUNTIME_REQ + TEST_REQ)],
                phase='install', name='install_runtime_deps', env=pip_env)
    session.run([str(ipy), '-m', 'pip', 'install', '--no-index', '--no-deps',
                 str(wheel)],
                phase='install', name='install_source_wheel', env=pip_env)

    # 4) standalone consumer venv under /workspace/consumer/venv
    consumer_venv = session.consumer / 'venv'
    session.run([sys.executable, '-m', 'venv', str(consumer_venv)],
                phase='consumer', name='create_consumer_venv')
    cpy = consumer_venv / 'bin' / 'python'
    session.run([str(cpy), '-m', 'pip', 'install', '--no-index', '--find-links',
                 str(WHEELHOUSE), *(RUNTIME_REQ + TEST_REQ)],
                phase='consumer', name='consumer_runtime_deps', env=pip_env)
    session.run([str(cpy), '-m', 'pip', 'install', '--no-index', '--no-deps',
                 str(wheel)],
                phase='consumer', name='consumer_install_wheel', env=pip_env)

    # 5) official tests, run from outside the source tree
    test_dir = session.consumer / 'test-run'
    test_dir.mkdir(parents=True, exist_ok=True)
    test_env = {
        'OMP_NUM_THREADS': '2',
        'OPENBLAS_NUM_THREADS': '2',
        'MKL_NUM_THREADS': '2',
        'NUMEXPR_NUM_THREADS': '2',
        'PYTHONDONTWRITEBYTECODE': '1',
    }
    session.run([str(cpy), '-m', 'pytest', '--pyargs',
                 'sklearn.neighbors.tests.test_kd_tree',
                 '--import-mode=importlib', '--collect-only', '-q',
                 '-p', 'no:cacheprovider'],
                cwd=str(test_dir), phase='official_test',
                name='kd_tree_inventory', env=test_env, timeout=600)
    session.test('sklearn.neighbors.tests.test_kd_tree',
                 [str(cpy), '-m', 'pytest', '--pyargs',
                  'sklearn.neighbors.tests.test_kd_tree',
                  '--import-mode=importlib', '-v', '-p', 'no:cacheprovider'],
                 cwd=str(test_dir), env=test_env, timeout=3600)

    # 6) consumer functional verification: KDTree and reloadable pipeline
    verify_dir = session.consumer / 'verify'
    verify_dir.mkdir(parents=True, exist_ok=True)
    session.run([str(cpy), str(scripts / 'consumer_fit.py'), str(verify_dir)],
                cwd=str(test_dir), phase='consumer', name='consumer_fit',
                env=test_env, timeout=900)
    session.run([str(cpy), str(scripts / 'consumer_reload.py'), str(verify_dir)],
                cwd=str(test_dir), phase='consumer', name='consumer_reload',
                env=test_env, timeout=900)

    session.finish(features={
        'wheel': str(wheel.relative_to(session.output)),
        'wheel_sha256': buildkit.digest(wheel),
        'scope_core': 'full native wheel + sklearn.neighbors.tests.test_kd_tree',
        'consumer_reload': True,
    })


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='build-scikit-learn',
        description='Source-build scikit-learn 1.6.1 wheel and verify KDTree + pipeline.')
    sub = parser.add_subparsers(dest='command')

    p_run = sub.add_parser('run', help='build, install, and verify')
    p_run.add_argument('--input', required=True)
    p_run.add_argument('--output', required=True)
    p_run.add_argument('--jobs', type=int, default=4)

    p_doc = sub.add_parser('doctor', help='report missing source/tool/dependency items')
    p_doc.add_argument('--input', required=True)

    args = parser.parse_args(argv)

    if args.command == 'doctor':
        missing = doctor(args.input)
        if missing:
            print('doctor: NOT READY -- %d missing item(s):' % len(missing))
            for item in missing:
                print('  -', item)
            return 78
        print('doctor: READY')
        return 0
    if args.command == 'run':
        run(args)
        return 0
    parser.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
