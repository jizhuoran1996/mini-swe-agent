#!/usr/bin/env python3
"""BUILDv1-F07: build the pandas 2.2.3 Cython distribution from source and verify it.

Usage:
  python3 solution/main.py --help
  python3 solution/main.py doctor --input input
  python3 solution/main.py run    --input input --output output --jobs 4
"""
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
RUN_DEPS = ['numpy', 'python-dateutil', 'pytz', 'tzdata']
TEST_DEPS = ['pytest', 'hypothesis', 'pytest-xdist', 'setuptools']
# Exact upstream [build-system].requires from pandas-2.2.3 pyproject.toml.
BUILD_REQS = ['meson-python==0.13.1', 'meson==1.2.1', 'wheel',
              'Cython~=3.0.5', 'numpy>=2.0', 'versioneer[toml]']


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


def _wheelhouse_names():
    names = set()
    if WHEELHOUSE.is_dir():
        for path in WHEELHOUSE.iterdir():
            if path.suffix == '.whl':
                head = path.name.split('-')[0]
                if head:
                    names.add(_norm(head))
    return names


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
    if not WHEELHOUSE.is_dir():
        missing.append(f'dependency wheelhouse {WHEELHOUSE}')
    else:
        available = _wheelhouse_names()
        for req in BUILD_REQS + ['build', 'pip', 'setuptools'] + RUN_DEPS + TEST_DEPS:
            name = _norm(re.split(r'[<>=!~;\[]', req)[0])
            if name not in available:
                missing.append(f'wheel in {WHEELHOUSE}: {req}')
    if missing:
        for item in missing:
            print('MISSING:', item)
        return 78
    print('doctor: source archive, toolchain and pinned offline build/test wheels all present')
    return 0


def _venv(session, path, name):
    """Create a virtualenv OUTSIDE the declared install root.

    The install root (/workspace/output/install) must contain package files
    only: no interpreter, no ``bin/`` symlink tree, no venv. This function
    hard-refuses any path that would place a venv under that root.
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


def _install_wheel(session, py, wheel, name, packages=()):
    session.run([str(py), '-m', 'pip', 'install', *PIP_FLAGS, '--no-deps', str(wheel)],
                phase='install', name=name, timeout=1800)
    if packages:
        session.run([str(py), '-m', 'pip', 'install', *PIP_FLAGS, *packages],
                    phase='install', name=f'{name}_deps', timeout=1800)


def _run_test(session, name, argv, **kwargs):
    """Run an upstream pytest suite, preserving evidence either way.

    A failing suite stays a failure: the exit code and full pytest log are
    recorded verbatim, and Session.finish() will refuse to declare success.
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

    # Large intermediates live on the workspace, not the small /tmp tmpfs.
    scratch = session.build / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    tests_cwd = session.build / 'tests'
    tests_cwd.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(scratch)

    # ---- bounded offline isolated build venv (outside output/install) ----
    bvenv = session.build / 'build-venv'
    bpy = _venv(session, bvenv, 'build')

    # PATH must have build-venv/bin FIRST in EVERY build-related command so the
    # genuinely installed pinned meson==1.2.1 / meson-python==0.13.1 win over
    # the global /opt/build-tools toolchain, and so the venv interpreter that
    # actually has versioneer[toml]+tomli runs generate_version.py.
    build_env = {
        'PATH': str(bvenv / 'bin') + os.pathsep + os.environ.get('PATH', ''),
        'NINJA_STATUS': '[%f/%t] ',
        'TMPDIR': str(scratch),
        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
    }

    session.run([str(bpy), '-m', 'pip', 'install', *PIP_FLAGS, *BUILD_REQS],
                phase='install', name='build_requirements', env=build_env, timeout=3600)
    session.run([str(bpy), '-m', 'pip', 'install', *PIP_FLAGS, 'build'],
                phase='install', name='build_frontend', env=build_env, timeout=1800)

    # ---- compile + link the source wheel (no isolation, pinned backend) ----
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

    # ---- runtime venv for the official tests, under /workspace/tools ----
    tools = Path('/workspace/tools')
    tools.mkdir(parents=True, exist_ok=True)
    ipy = _venv(session, tools / 'install-venv', 'install')
    _install_wheel(session, ipy, wheel, 'install_wheel', packages=RUN_DEPS + TEST_DEPS)

    # ---- declared install root: package files only (no venv, no interpreter) ----
    session.run([str(ipy), '-m', 'pip', 'install', *PIP_FLAGS, '--no-deps',
                 '--target', str(session.install), str(wheel)],
                phase='install', name='install_target', timeout=1800)

    # ---- frozen official core-scope upstream tests ----
    test_env = {'PANDAS_CI': '1', 'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2',
                'MKL_NUM_THREADS': '2', 'NUMEXPR_NUM_THREADS': '2',
                'TMPDIR': str(scratch)}
    _run_test(
        session, 'pandas.tests.libs + pandas.tests.tslibs',
        [str(ipy), '-m', 'pytest', '--pyargs', 'pandas.tests.libs', 'pandas.tests.tslibs',
         '-m', 'not network and not db', '-n', '2', '-q', '--tb=short',
         '-p', 'no:cacheprovider'],
        cwd=str(tests_cwd), env=test_env, timeout=10800)

    # ---- independent consumer venv, outside src, output and install root ----
    cpy = _venv(session, session.consumer / 'venv', 'consumer')
    _install_wheel(session, cpy, wheel, 'consumer_wheel', packages=RUN_DEPS)
    try:
        session.run([str(cpy), '-m', 'pip', 'install', *PIP_FLAGS, 'pyarrow'],
                    phase='install', name='consumer_pyarrow', timeout=1800)
    except RuntimeError:
        pass

    data = out / 'consumer_data'
    data.mkdir(parents=True, exist_ok=True)
    consumer = Path(__file__).resolve().parent / 'consumer.py'
    session.run([str(cpy), str(consumer), 'build', '--outdir', str(data)],
                cwd=str(session.consumer), phase='consumer', name='consumer_build', timeout=1200)
    session.run([str(cpy), str(consumer), 'reload', '--outdir', str(data)],
                cwd=str(session.consumer), phase='consumer', name='consumer_reload', timeout=1200)

    session.finish(features={
        'wheel': wheel.name,
        'native_extensions': 'pandas._libs',
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
