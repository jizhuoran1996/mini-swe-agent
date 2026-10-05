#!/usr/bin/env python3
"""CPU jaxlib + JAX source build orchestrator (BUILDv1-F03 core profile)."""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit

BAZEL_PATH = '/opt/bazel/7.4.1/bazel'
BAZEL_REPO_CACHE = '/workspace/cache/bazel_repository'
BAZEL_OUTPUT_BASE = '/workspace/cache/bazel_output'
BAZEL_EXTERNAL = '/workspace/cache/bazel_output/external'
HEAVY_RAM_MB = '24000'

REQUIRED_TOOLS = ['clang', 'clang++', 'python3', 'patch', 'git']
REQUIRED_PYMODULES = [
    'numpy', 'scipy', 'setuptools', 'wheel', 'build', 'ml_dtypes',
    'opt_einsum', 'zstandard', 'flatbuffers', 'absl', 'typing_extensions',
    'packaging', 'importlib_metadata',
]
FIXED_CPU_WHEELS = [
    'numpy', 'scipy', 'ml_dtypes', 'opt_einsum', 'absl_py', 'typing_extensions',
    'packaging', 'hypothesis', 'pytest', 'setuptools', 'wheel', 'build',
]
ACCELERATOR_TOKENS = (
    'nvidia', 'cuda', 'cudnn', 'cublas', 'cusolver', 'cusparse', 'cufft',
    'curand', 'nccl', 'nvjitlink', 'triton', 'libtpu', 'jax_cuda', 'jax_rocm',
    'rocm',
)


def _read_manifest(input_dir):
    path = Path(input_dir) / 'manifest.json'
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _check_source(input_dir, manifest):
    problems = []
    if manifest is None:
        problems.append(f'missing manifest.json in {input_dir}')
        return problems
    src = manifest.get('source', {})
    filename = src.get('filename')
    if not filename:
        problems.append('manifest source.filename missing')
        return problems
    archive = Path(input_dir) / filename
    if not archive.exists():
        problems.append(f'missing source archive: {archive}')
    else:
        expected = src.get('sha256')
        if expected and buildkit.digest(archive) != expected:
            problems.append(f'source archive sha256 mismatch: {archive}')
    return problems


def _check_tools():
    return [f'missing executable: {t}' for t in REQUIRED_TOOLS if shutil.which(t) is None]


def _check_pymodules():
    return [f'missing python module: {m}' for m in REQUIRED_PYMODULES
            if importlib.util.find_spec(m) is None]


def _check_bazel_prepared():
    problems = []
    if not (Path(BAZEL_PATH).is_file() and os.access(BAZEL_PATH, os.X_OK)):
        problems.append(f'missing bazel 7.4.1 executable: {BAZEL_PATH}')
    for label, path in (('bazel repository cache', BAZEL_REPO_CACHE),
                        ('bazel output_base external tree', BAZEL_EXTERNAL)):
        p = Path(path)
        if not p.is_dir() or not any(p.iterdir()):
            problems.append(f'missing prepared {label}: {path}')
    return problems


def _is_cpu_requirement(name):
    if name in ('jax', 'jaxlib'):
        return False
    return not any(tok in name for tok in ACCELERATOR_TOKENS)


def _parse_requirement_names(text):
    """PEP 508 distribution names: continuations, option flags, extras, markers."""
    names = set()
    joined = re.sub(r'\\\s*\n', ' ', text)
    for raw in joined.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line or line.startswith('-'):
            continue
        token = line.split()[0]
        if token.startswith('-'):
            continue
        if '@' in token:
            token = token.split('@', 1)[0]
        token = token.split(';', 1)[0].split('[', 1)[0]
        for sep in ('===', '==', '<=', '>=', '~=', '!=', '=', '<', '>'):
            if sep in token:
                token = token.split(sep, 1)[0]
                break
        token = token.strip()
        if not token or not re.match(r'^[A-Za-z0-9][A-Za-z0-9._-]*$', token):
            continue
        names.add(token.lower().replace('-', '_'))
    return names


def _read_archive_members(archive, wanted_names):
    out = {}
    try:
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                parts = Path(member.name).parts
                if len(parts) >= 3 and parts[1] == 'build' and parts[2] in wanted_names:
                    handle = tf.extractfile(member)
                    if handle is not None:
                        out[parts[2]] = handle.read().decode(errors='replace')
    except Exception:
        pass
    return out


def _check_wheelhouse(archive):
    problems = []
    wh = Path('/opt/wheelhouse')
    if not wh.is_dir():
        return [f'missing wheelhouse directory: {wh}']
    names = [p.name.lower().replace('-', '_') for p in wh.iterdir() if p.is_file()]
    required = set(FIXED_CPU_WHEELS)
    texts = _read_archive_members(
        archive, ['test-requirements.txt', 'requirements_lock_3_12.txt'])
    for text in texts.values():
        required.update(_parse_requirement_names(text))
    required = {n for n in required if _is_cpu_requirement(n)}
    for pkg in sorted(required):
        if not any(n.startswith(pkg) for n in names):
            problems.append(f'missing CPU wheel in {wh}: {pkg}')
    return problems


def _check_venv():
    problems = []
    tmp = Path('/tmp') / f'bv103_venv_probe_{os.getpid()}'
    try:
        subprocess.run([sys.executable, '-m', 'venv', str(tmp)],
                       check=True, capture_output=True, timeout=180)
    except Exception as exc:
        problems.append(f'python venv creation failed: {exc}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return problems


def doctor(input_dir):
    manifest = _read_manifest(input_dir)
    problems = []
    problems += _check_source(input_dir, manifest)
    problems += _check_tools()
    problems += _check_pymodules()
    problems += _check_bazel_prepared()
    archive = Path(input_dir) / (manifest or {}).get('source', {}).get('filename', '')
    if archive.exists():
        problems += _check_wheelhouse(archive)
    else:
        problems.append('cannot check wheelhouse without source archive')
    problems += _check_venv()
    if problems:
        print(json.dumps({'status': 'missing', 'problems': problems}, indent=2))
        return 78
    print(json.dumps({'status': 'ready'}, indent=2))
    return 0


def run(args):
    session = buildkit.Session(args.input, args.output, args.jobs)
    session.prepare()
    src = session.src
    out = session.output
    jobs = str(min(session.jobs, 4))

    for label, path in (('bazel repository cache', BAZEL_REPO_CACHE),
                        ('bazel external tree', BAZEL_EXTERNAL)):
        if not Path(path).is_dir():
            raise RuntimeError(f'prepared {label} missing; run doctor first: {path}')
    if not Path(BAZEL_PATH).is_file():
        raise RuntimeError(f'prepared bazel missing: {BAZEL_PATH}')

    build_env = {
        'JAX_PLATFORMS': 'cpu',
        'JAX_ENABLE_X64': 'true',
        'JAX_NUM_GENERATED_CASES': '1',
        'JAX_RELEASE': '1',
    }

    build_cmd = [
        sys.executable, 'build/build.py', 'build', '--wheels=jaxlib',
        '--python_version=3.12',
        f'--bazel_path={BAZEL_PATH}',
        f'--bazel_startup_options=--output_base={BAZEL_OUTPUT_BASE}',
        f'--bazel_options=--repository_cache={BAZEL_REPO_CACHE}',
        f'--bazel_options=--jobs={jobs}',
        f'--bazel_options=--local_ram_resources={HEAVY_RAM_MB}',
    ]
    session.run(build_cmd, cwd=src, phase='build', name='jaxlib_build',
                env=build_env, timeout=10800)

    jaxlib_wheels = sorted((src / 'dist').glob('jaxlib-*.whl'))
    if not jaxlib_wheels:
        raise RuntimeError('jaxlib build produced no wheel in src/dist')
    jaxlib_wheel = jaxlib_wheels[-1]

    session.run(
        [sys.executable, '-m', 'build', '--wheel', '--no-isolation',
         '--outdir', str(out), str(src)],
        cwd=src, phase='package', name='jax_wheel', env=build_env, timeout=3600)
    jax_wheels = sorted(out.glob('jax-*.whl'))
    if not jax_wheels:
        raise RuntimeError('JAX frontend build produced no wheel')
    jax_wheel = jax_wheels[-1]
    shutil.copy2(jaxlib_wheel, out / jaxlib_wheel.name)

    venv_dir = Path('/workspace/consumer/venv')
    session.run([sys.executable, '-m', 'venv', str(venv_dir)],
                cwd='/workspace/consumer', phase='install', name='create_venv',
                timeout=300)
    py = str(venv_dir / 'bin' / 'python')

    session.run(
        [py, '-m', 'pip', 'install', '--no-index', '--find-links', '/opt/wheelhouse',
         '--no-deps', str(jaxlib_wheel)],
        cwd='/workspace/consumer', phase='install', name='install_jaxlib', timeout=900)
    session.run(
        [py, '-m', 'pip', 'install', '--no-index', '--find-links', '/opt/wheelhouse',
         '--no-deps', str(jax_wheel)],
        cwd='/workspace/consumer', phase='install', name='install_jax', timeout=900)
    session.run(
        [py, '-m', 'pip', 'install', '--no-index', '--find-links', '/opt/wheelhouse',
         'numpy', 'scipy', 'ml_dtypes', 'opt_einsum', 'absl-py',
         'typing_extensions', 'packaging', 'hypothesis', 'pytest'],
        cwd='/workspace/consumer', phase='install', name='install_runtime_deps',
        timeout=900)

    test_file = src / 'tests' / 'lax_numpy_test.py'
    if not test_file.exists():
        raise RuntimeError(f'official test file missing: {test_file}')
    session.test(
        'lax_numpy_test_pad',
        [py, str(test_file), '--test_targets=testPad'],
        cwd='/workspace/consumer', parser='auto',
        env={'JAX_PLATFORMS': 'cpu', 'JAX_ENABLE_X64': 'true'}, timeout=2400)

    consumer_script = Path(__file__).resolve().parent / 'consumer_check.py'
    session.run([py, str(consumer_script)],
                cwd='/workspace/consumer', phase='consumer', name='functional_consumer',
                env={'JAX_PLATFORMS': 'cpu'}, timeout=600)

    session.finish(features={
        'profile': 'core',
        'scope': 'CPU jaxlib+JAX',
        'bazel': BAZEL_PATH,
        'bazel_repository_cache': BAZEL_REPO_CACHE,
        'bazel_output_base': BAZEL_OUTPUT_BASE,
        'jaxlib_wheel': str(jaxlib_wheel),
        'jax_wheel': str(jax_wheel),
        'official_test': 'lax_numpy_test.py --test_targets=testPad',
    })


def main(argv=None):
    parser = argparse.ArgumentParser(prog='BUILDv1-F03',
                                     description='CPU jaxlib+JAX source build')
    sub = parser.add_subparsers(dest='command', required=True)
    doctor_p = sub.add_parser('doctor', help='check offline prerequisites')
    doctor_p.add_argument('--input', required=True)
    run_p = sub.add_parser('run', help='build, install, test')
    run_p.add_argument('--input', required=True)
    run_p.add_argument('--output', required=True)
    run_p.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        return doctor(args.input)
    if args.command == 'run':
        try:
            run(args)
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 1
        return 0
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
