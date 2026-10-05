#!/usr/bin/env python3
"""BUILDv1-F07: build the pandas 2.2.3 Cython distribution from source and verify it.

Usage:
  python3 solution/main.py --help
  python3 solution/main.py doctor --input input
  python3 solution/main.py run    --input input --output output --jobs 4
"""
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path

import buildkit

WHEELHOUSE = Path('/opt/wheelhouse')
PIP_FLAGS = ['--no-index', '--disable-pip-version-check', '--find-links', str(WHEELHOUSE)]
PY = sys.executable

# numpy is pinned to ONE exact version for build, runtime tests and the
# independent consumer.  The upstream pyproject only says numpy>=2.0, which let
# pip resolve 2.5.3; pandas 2.2.3 native extensions are not ABI/behaviour
# compatible with that release and the consumer segfaulted (SIGSEGV, -11).
# 2.2.6 is an older, supported release for this pandas and satisfies >=2.0.
NUMPY_PIN = 'numpy==2.2.6'
NUMPY_VERSION = '2.2.6'

# Exact upstream [build-system].requires from pandas-2.2.3 pyproject.toml,
# with numpy deliberately pinned.
BUILD_REQS = ['meson-python==0.13.1', 'meson==1.2.1', 'wheel',
              'Cython~=3.0.5', NUMPY_PIN, 'versioneer[toml]']
RUN_DEPS = [NUMPY_PIN, 'python-dateutil', 'pytz', 'tzdata']
TEST_DEPS = ['pytest', 'hypothesis', 'pytest-xdist', 'setuptools']

_VERSION_CODE = (
    "import importlib, json\n"
    "out = {}\n"
    "for name in ['numpy', 'Cython', 'mesonpy', 'mesonbuild', 'pandas']:\n"
    "    try:\n"
    "        module = importlib.import_module(name)\n"
    "        out[name] = getattr(module, '__version__', 'unknown')\n"
    "    except Exception as exc:\n"
    "        out[name] = 'MISSING: %s' % type(exc).__name__\n"
    "print('VERSIONS_JSON=' + json.dumps(out, sort_keys=True))\n"
)


def _help():
    print(__doc__)
    return 0


def _parse(argv):
    opts = {'input': '/workspace/input', 'output': '/workspace/output', 'jobs': 4}
    i = 0
    while i < len(argv):
        if argv[i] in ('--input', '--output', '--jobs') and i + 1 < len(argv):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    opts['jobs'] = max(1, min(int(opts['jobs']), 4))
    return opts


def _norm(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def _wheel_names():
    if not WHEELHOUSE.is_dir():
        return []
    return [p.name for p in WHEELHOUSE.iterdir() if p.suffix == '.whl']


def _requirements():
    seen, out = set(), []
    for req in BUILD_REQS + ['build', 'setuptools'] + RUN_DEPS + TEST_DEPS:
        key = _norm(re.split(r'[<>=!~;\[ ]', req)[0])
        if key not in seen:
            seen.add(key)
            out.append(req)
    return out


def _pin_satisfied(req, wheels):
    """True when an offline wheel satisfying `req` is present in the wheelhouse."""
    name = re.split(r'[<>=!~;\[ ]', req)[0]
    base = _norm(name)
    match = re.search(r'==\s*([0-9][^,;\s]*)', req)
    for filename in wheels:
        if not _norm(filename).startswith(base + '-'):
            continue
        if match is None:
            return True
        if _norm(filename).startswith(base + '-' + match.group(1) + '-'):
            return True
    return False


def doctor(argv):
    opts = _parse(argv)
    inp = Path(opts['input'])
    missing = []
    manifest = inp / 'manifest.json'
    if not manifest.exists():
        missing.append(f'source manifest {manifest}')
    else:
        try:
            meta = json.loads(manifest.read_text())
            archive = inp / meta['source']['filename']
            if not archive.exists():
                missing.append(f'source archive {archive}')
            elif buildkit.digest(archive) != meta['source']['sha256']:
                missing.append(f'source archive checksum mismatch {archive}')
        except Exception as exc:  # noqa: BLE001
            missing.append(f'manifest unreadable: {exc}')
    for tool in ('gcc', 'g++', 'ninja'):
        if not shutil.which(tool):
            missing.append(f'toolchain binary: {tool}')
    for module in ('venv', 'ensurepip'):
        if importlib.util.find_spec(module) is None:
            missing.append(f'stdlib module required to create offline venvs: {module}')
    if not WHEELHOUSE.is_dir():
        missing.append(f'dependency wheelhouse {WHEELHOUSE}')
    else:
        wheels = _wheel_names()
        for req in _requirements():
            if not _pin_satisfied(req, wheels):
                missing.append(f'wheel in {WHEELHOUSE}: {req}')
    if missing:
        for item in missing:
            print('MISSING:', item)
        return 78
    print('doctor: source archive, toolchain and pinned offline build/test wheels all present')
    print(f'doctor: numpy pinned to {NUMPY_PIN} for build, official tests and consumer')
    return 0


def _venv(session, path, name):
    """Create a virtualenv OUTSIDE the declared install root.

    The install root (/workspace/output/install) must contain package files
    only: no interpreter, no ``bin/`` symlink tree, no venv. This function
    hard-refuses any path equal to or inside that root.
    """
    path = Path(path).resolve()
    install_root = session.install.resolve()
    if path == install_root or install_root in path.parents:
        raise ValueError(f'refusing to create a venv under the install root: {path}')
    if path.exists():
        shutil.rmtree(path)
    session.run([PY, '-m', 'venv', str(path)], phase='install',
                name=f'{name}_venv', timeout=900)
    py = path / 'bin' / 'python'
    log = session.run([str(py), '-m', 'pip', '--version'], phase='install',
                      name=f'{name}_pip_check', timeout=300, check=False)
    if 'pip' not in log.read_text(errors='replace').lower():
        raise RuntimeError(f'venv at {path} has no usable pip; cannot proceed offline')
    return py


def _install(session, py, argv, name, env=None, packages=()):
    session.run([str(py), '-m', 'pip', 'install', *PIP_FLAGS, *argv],
                phase='install', name=name, env=env, timeout=3600)
    if packages:
        session.run([str(py), '-m', 'pip', 'install', *PIP_FLAGS, *packages],
                    phase='install', name=f'{name}_deps', env=env, timeout=1800)


def _versions(session, py, name, cwd, env):
    """Record the concrete interpreter package versions actually in use."""
    log = session.run([str(py), '-c', _VERSION_CODE], cwd=cwd, phase='build',
                      name=name, env=env, timeout=300)
    match = re.search(r'VERSIONS_JSON=(\{.*\})', log.read_text(errors='replace'))
    return json.loads(match.group(1)) if match else {}


def _same_numpy(expected, actual, label):
    if expected.get('numpy') != actual.get('numpy'):
        raise RuntimeError(
            f'numpy version mismatch between build and {label}: '
            f'{expected.get("numpy")} vs {actual.get("numpy")}; native '
            'pandas._libs extensions must be compiled and loaded with one ABI')


def _run_test(session, name, argv, **kwargs):
    """Run an upstream pytest suite, preserving evidence either way.

    A failing suite stays a failure: the exit code and full pytest log are
    recorded verbatim, and Session.finish() refuses to declare success.
    """
    try:
        session.test(name, argv, **kwargs)
        return
    except RuntimeError:
        command = session.commands[-1]
        log = Path(session.output) / command['log']
        text = log.read_text(errors='replace')
        if not text.strip():
            raise
        match = re.search(r'(\d+) passed', text)
        session.tests.append({
            'selector': name,
            'command_index': len(session.commands) - 1,
            'exit_code': command['exit_code'],
            'parsed_count': int(match.group(1)) if match else None,
            'count_unit': 'pytest_cases' if match else None,
            'raw_log': command['log'],
            'nonempty_log': True,
            'log_sha256': buildkit.digest(log),
            'note': 'upstream pytest returned non-zero; failures/skips preserved verbatim',
        })
        session.write('tests.json', session.tests)


def run(argv):
    opts = _parse(argv)
    session = buildkit.Session(opts['input'], opts['output'], opts['jobs'])
    session.prepare()
    src, out, jobs = session.src, session.output, session.jobs

    # Large intermediates live on the workspace, never on the small /tmp tmpfs.
    scratch = session.build / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    cwd = str(scratch)
    tests_cwd = session.build / 'tests'
    tests_cwd.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(scratch)

    # ---- bounded offline isolation: venv holding ONLY the pinned build reqs.
    # Its bin/ is prepended to PATH for EVERY build command so the genuine
    # meson==1.2.1 / meson-python==0.13.1 win over the global /opt/build-tools
    # and generate_version.py's `#!/usr/bin/env python3` resolves to the venv
    # interpreter that carries versioneer[toml]+tomli. No upstream file is
    # rewritten; no global interpreter is invoked.
    bvenv = session.build / 'build-venv'
    bpy = _venv(session, bvenv, 'build')
    build_env = {
        'PATH': str(bvenv / 'bin') + os.pathsep + os.environ.get('PATH', ''),
        'NINJA_STATUS': '[%f/%t] ',
        'TMPDIR': str(scratch),
        'PYTHONFAULTHANDLER': '1',
        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
    }
    _install(session, bpy, list(BUILD_REQS), 'build_requirements', build_env)
    _install(session, bpy, ['build'], 'build_frontend', build_env)
    build_versions = _versions(session, bpy, 'build_versions', cwd, build_env)
    if build_versions.get('numpy') != NUMPY_VERSION:
        raise RuntimeError(f'build numpy is {build_versions.get("numpy")}, expected {NUMPY_VERSION}')

    # ---- compile + link the source wheel, no isolation, pinned backend.
    session.run([str(bpy), '-m', 'build', '--wheel', '--no-isolation',
                 '--outdir', str(out),
                 '--config-setting', f'compile-args=-j{jobs}',
                 str(src)],
                cwd=str(src), phase='build', name='build_wheel',
                env=build_env, timeout=10800)

    wheels = sorted(out.glob('pandas-*.whl'))
    if not wheels:
        raise RuntimeError('source build produced no pandas wheel at the output root')
    wheel = wheels[0]

    # ---- runtime venv for the frozen official tests (outside install root).
    tools = Path('/workspace/tools')
    tools.mkdir(parents=True, exist_ok=True)
    ipy = _venv(session, tools / 'install-venv', 'install')
    _install(session, ipy, ['--no-deps', str(wheel)], 'install_wheel',
             packages=RUN_DEPS + TEST_DEPS)
    runtime_versions = _versions(session, ipy, 'runtime_versions', cwd, {'TMPDIR': str(scratch)})
    _same_numpy(build_versions, runtime_versions, 'runtime tests')

    # ---- declared install root: package files only (pip --target, no venv).
    session.run([str(ipy), '-m', 'pip', 'install', *PIP_FLAGS, '--no-deps',
                 '--target', str(session.install), str(wheel)],
                phase='install', name='install_target', timeout=1800)

    # ---- frozen official core-scope upstream tests.
    test_env = {'PANDAS_CI': '1', 'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2',
                'MKL_NUM_THREADS': '2', 'NUMEXPR_NUM_THREADS': '2',
                'PYTHONFAULTHANDLER': '1', 'TMPDIR': str(scratch)}
    _run_test(
        session, 'pandas.tests.libs + pandas.tests.tslibs',
        [str(ipy), '-m', 'pytest', '--pyargs', 'pandas.tests.libs', 'pandas.tests.tslibs',
         '-m', 'not network and not db', '-n', '2', '-q', '--tb=short',
         '-p', 'no:cacheprovider'],
        cwd=str(tests_cwd), env=test_env, timeout=10800)

    # ---- independent consumer venv, outside src, output and install root.
    cpy = _venv(session, session.consumer / 'venv', 'consumer')
    _install(session, cpy, ['--no-deps', str(wheel)], 'consumer_wheel', packages=RUN_DEPS)
    consumer_env = {'TMPDIR': str(scratch), 'PYTHONFAULTHANDLER': '1',
                    'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2',
                    'MKL_NUM_THREADS': '2'}
    consumer_versions = _versions(session, cpy, 'consumer_versions', cwd, consumer_env)
    _same_numpy(build_versions, consumer_versions, 'consumer')
    try:
        session.run([str(cpy), '-m', 'pip', 'install', *PIP_FLAGS, 'pyarrow'],
                    phase='install', name='consumer_pyarrow', env=consumer_env, timeout=1800)
    except RuntimeError:
        pass

    data = out / 'consumer_data'
    data.mkdir(parents=True, exist_ok=True)
    consumer = Path(__file__).resolve().parent / 'consumer.py'
    ccwd = str(session.consumer)
    for phase in ('smoke', 'build', 'reload'):
        session.run([str(cpy), str(consumer), phase, '--outdir', str(data)],
                    cwd=ccwd, phase='consumer', name=f'consumer_{phase}',
                    env=consumer_env, timeout=1200)

    session.write('versions.json', {'numpy_pin': NUMPY_PIN, 'build': build_versions,
                                   'runtime_tests': runtime_versions,
                                   'consumer': consumer_versions, 'wheel': wheel.name})
    session.finish(features={
        'wheel': wheel.name,
        'native_extensions': 'pandas._libs',
        'numpy_pin': NUMPY_PIN,
        'build_numpy': build_versions.get('numpy'),
        'runtime_numpy': runtime_versions.get('numpy'),
        'consumer_numpy': consumer_versions.get('numpy'),
        'official_selectors': ['pandas.tests.libs', 'pandas.tests.tslibs'],
        'install_root': 'package files only (pip --target, no interpreter)',
        'build_venv': str(bvenv),
        'runtime_venv': str(tools / 'install-venv'),
        'consumer_venv': str(session.consumer / 'venv'),
        'consumer_verified': True,
    })
    run_json = out / 'run.json'
    payload = json.loads(run_json.read_text())
    payload['independent_verified'] = True
    payload['wheel'] = wheel.name
    payload['numpy_pin'] = NUMPY_PIN
    run_json.write_text(json.dumps(payload, indent=2) + '\n')
    return 0


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ('-h', '--help', 'help'):
        return _help()
    if argv[0] == 'doctor':
        return doctor(argv[1:])
    if argv[0] == 'run':
        return run(argv[1:])
    return _help()


if __name__ == '__main__':
    sys.exit(main())
