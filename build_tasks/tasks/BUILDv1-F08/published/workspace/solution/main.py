#!/usr/bin/env python3
"""BUILDv1-F08: build the XGBoost CPU native core and Python wheel from frozen source."""
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

from buildkit import Session, digest

HERE = Path(__file__).resolve().parent
WHEELHOUSE = Path('/opt/wheelhouse')
# Genuine test-only dependencies for the unmodified official tests/python/test_basic.py.
# xgboost.testing uses importorskip and sklearn.datasets, so hypothesis and
# scikit-learn are real required test dependencies (never target wheels).
TEST_DEPS = ['pytest', 'hypothesis', 'scikit-learn', 'pandas']


def cmd_doctor(input_dir):
    missing = []
    inp = Path(input_dir)
    manifest = inp / 'manifest.json'
    if not manifest.is_file():
        missing.append(f'manifest: {manifest}')
    else:
        try:
            entry = json.loads(manifest.read_text())['source']
            archive = inp / entry['filename']
            if not archive.is_file():
                missing.append(f'source archive: {archive}')
            elif digest(archive) != entry['sha256']:
                missing.append(f'source archive checksum mismatch: {archive}')
        except Exception as exc:
            missing.append(f'manifest parse error: {exc}')
    for tool in ('cmake', 'ninja', 'cc', 'c++', 'python3'):
        if shutil.which(tool) is None:
            missing.append(f'tool: {tool}')
    if not WHEELHOUSE.is_dir():
        missing.append(f'wheelhouse directory: {WHEELHOUSE}')
    else:
        wheels = list(WHEELHOUSE.glob('*.whl'))
        if not wheels:
            missing.append(f'wheelhouse wheels: {WHEELHOUSE}')
        for requirement in ('numpy', 'scipy', 'pandas', 'scikit_learn', 'hypothesis', 'pytest'):
            if not any(w.name.lower().startswith(requirement) for w in wheels):
                missing.append(f'wheelhouse package: {requirement}')
    if missing:
        for item in missing:
            print('MISSING: ' + item)
        return 78
    print('READY: source archive, native toolchain, and offline wheelhouse present')
    return 0


def cmd_run(input_dir, output_dir, jobs):
    session = Session(input_dir, output_dir, jobs)
    session.prepare()
    src, build, install, out = session.src, session.build, session.install, session.output
    parallel = session.jobs
    omp = str(min(parallel, 2))
    env = {'OMP_NUM_THREADS': omp, 'CMAKE_BUILD_PARALLEL_LEVEL': str(parallel)}

    session.run([
        'cmake', '-S', str(src), '-B', str(build), '-GNinja',
        '-DCMAKE_BUILD_TYPE=Release', '-DUSE_CUDA=OFF', '-DGOOGLE_TEST=ON',
        '-DUSE_OPENMP=ON', '-DBUILD_STATIC_LIB=OFF', '-DBUILD_DEPRECATED_CLI=OFF',
        '-DPLUGIN_FEDERATED=OFF', '-DJVM_BINDINGS=OFF', '-DR_LIB=OFF',
        '-DUSE_NCCL=OFF', '-DKEEP_BUILD_ARTIFACTS_IN_BINARY_DIR=OFF',
        f'-DCMAKE_INSTALL_PREFIX={install}',
    ], phase='configure', name='cmake_configure', env=env, timeout=1800)

    session.run(['cmake', '--build', str(build), '--parallel', str(parallel)],
                phase='build', name='cmake_build', env=env, timeout=10800)

    lib = src / 'lib' / 'libxgboost.so'
    if not lib.is_file():
        alt = build / 'lib' / 'libxgboost.so'
        if alt.is_file():
            lib = alt
        else:
            raise RuntimeError('libxgboost.so missing after native build')
    native_sha = digest(lib)
    print(f'native core: {lib} sha256={native_sha}')

    session.run(['cmake', '--install', str(build)],
                phase='install', name='cmake_install', env=env, timeout=600)

    session.test('ctest_TestXGBoostLib',
                 ['ctest', '--test-dir', str(build), '--output-on-failure',
                  '-R', '^TestXGBoostLib$'],
                 cwd=str(build), parser='ctest_cases', env=env, timeout=5400)

    build_venv = Path('/workspace/build-venv')
    session.run([sys.executable, '-m', 'venv', str(build_venv)],
                phase='package', name='create_build_venv', timeout=300)
    bpy = build_venv / 'bin' / 'python'
    session.run([str(bpy), '-m', 'pip', 'install', '--no-index',
                 '--find-links', str(WHEELHOUSE), 'build', 'hatchling', 'packaging'],
                phase='package', name='build_backend', timeout=900)

    # Use the official upstream generator to emit a legitimate CPU-only
    # pyproject.toml (and matching README) from the shipped template. Keeping
    # the `xgboost` name (use-cpu-suffix=0) and dropping the hard NCCL
    # requirement (require-nccl-dep=0) is a supported upstream configuration,
    # not a removed dependency. No manual metadata patching.
    gen = src / 'ops' / 'script' / 'pypi_variants.py'
    if not gen.is_file():
        raise RuntimeError(f'missing upstream generator: {gen}')
    help_log = session.run([str(bpy), str(gen), '--help'], cwd=str(src),
                           phase='package', name='pypi_variants_help',
                           check=False, timeout=300)
    help_text = help_log.read_text(errors='replace')
    gen_args = ['--use-cpu-suffix=0', '--require-nccl-dep=0']
    if '--src-dir' in help_text:
        gen_args = ['--src-dir', str(src)] + gen_args
    session.run([str(bpy), str(gen)] + gen_args, cwd=str(src),
                phase='package', name='pypi_variants', timeout=600)

    session.run([str(bpy), '-m', 'build', '--wheel', '--no-isolation',
                 '--outdir', str(out), str(src / 'python-package')],
                cwd=str(out), phase='package', name='build_wheel', env=env, timeout=7200)

    wheels = sorted(out.glob('*.whl'))
    if not wheels:
        raise RuntimeError('python wheel was not produced')
    wheel = wheels[-1]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if not any(n.endswith('libxgboost.so') for n in names):
            raise RuntimeError('wheel does not embed the freshly built libxgboost.so')
        member = next(n for n in names if n.endswith('libxgboost.so'))
        wheel_lib_sha = hashlib.sha256(archive.read(member)).hexdigest()
        meta_name = next(n for n in names if n.endswith('.dist-info/METADATA'))
        meta = archive.read(meta_name).decode('utf-8', 'replace')
    if wheel_lib_sha != native_sha:
        raise RuntimeError(
            f'wheel libxgboost.so hash {wheel_lib_sha} != built {native_sha}')
    name_line = next((l.split(':', 1)[1].strip() for l in meta.splitlines()
                      if l.startswith('Name:')), '')
    if name_line != 'xgboost':
        raise RuntimeError(f'unexpected wheel package name: {name_line!r}')
    requires = [l.split(':', 1)[1].strip() for l in meta.splitlines()
                if l.lower().startswith('requires-dist:')]
    nccl = [r for r in requires if 'nvidia-nccl' in r.lower() and 'extra ==' not in r]
    if nccl:
        raise RuntimeError(f'wheel still hard-requires NCCL: {nccl}')
    print(f'wheel: {wheel} embeds libxgboost.so sha256={wheel_lib_sha}')
    print(f'wheel requires-dist: {requires}')

    venv = session.consumer / 'venv'
    session.run([sys.executable, '-m', 'venv', str(venv)],
                phase='install', name='create_consumer_venv', timeout=300)
    cpy = venv / 'bin' / 'python'
    # Real, dependency-resolving install exactly like an external consumer.
    session.run([str(cpy), '-m', 'pip', 'install', '--no-index',
                 '--find-links', str(WHEELHOUSE), '--find-links', str(out),
                 str(wheel)],
                phase='install', name='install_wheel', timeout=1200)
    session.run([str(cpy), '-m', 'pip', 'install', '--no-index',
                 '--find-links', str(WHEELHOUSE)] + TEST_DEPS,
                phase='install', name='consumer_test_deps', timeout=1800)

    consumer = session.consumer / 'consumer.py'
    shutil.copy(str(HERE / 'consumer.py'), str(consumer))
    model = session.consumer / 'model.ubj'
    session.run([str(cpy), str(consumer), str(model)],
                cwd=str(session.consumer), phase='consumer',
                name='consumer_train_save', env={'OMP_NUM_THREADS': omp}, timeout=600)
    session.run([str(cpy), str(consumer), str(model), '--load'],
                cwd=str(session.consumer), phase='consumer',
                name='consumer_reload_predict', env={'OMP_NUM_THREADS': omp}, timeout=600)

    # Official Python test suite (unmodified upstream file). Must actually
    # collect and pass; an empty/all-skipped pytest run (exit code 5) is
    # rejected inside Session.test(), never reported as success.
    session.test('pytest_test_basic',
                 [str(cpy), '-m', 'pytest', '-p', 'no:cacheprovider', '-v',
                  '--import-mode=importlib',
                  str(src / 'tests' / 'python' / 'test_basic.py')],
                 cwd=str(src), parser='pytest_cases',
                 env={'OMP_NUM_THREADS': omp}, timeout=1800)

    session.write('packaging.json', {
        'native_lib': str(lib), 'native_sha256': native_sha,
        'wheel': wheel.name, 'wheel_sha256': digest(wheel),
        'wheel_embedded_lib_sha256': wheel_lib_sha,
        'wheel_embeds_libxgboost': True,
        'wheel_name': name_line,
        'requires_dist': requires,
        'nccl_hard_required': False,
        'hash_match': wheel_lib_sha == native_sha,
        'consumer_venv': str(venv),
        'test_deps': TEST_DEPS,
    })
    session.finish(features={'cuda': False, 'openmp': True, 'gtest': True,
                             'python_wheel': True, 'cpu_only_metadata': True,
                             'scope': 'core'})


def main():
    parser = argparse.ArgumentParser(prog='buildv1-f08',
                                     description='XGBoost CPU core + wheel builder')
    sub = parser.add_subparsers(dest='cmd')
    run = sub.add_parser('run', help='build, package, install and test')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    doc = sub.add_parser('doctor', help='preflight checks')
    doc.add_argument('--input', required=True)
    args = parser.parse_args()
    if args.cmd == 'doctor':
        return cmd_doctor(args.input)
    if args.cmd == 'run':
        cmd_run(args.input, args.output, args.jobs)
        return 0
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
