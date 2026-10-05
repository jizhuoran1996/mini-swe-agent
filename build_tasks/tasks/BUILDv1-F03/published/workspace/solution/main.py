#!/usr/bin/env python3
"""CPU jaxlib + JAX source build orchestrator (BUILDv1-F03 core profile)."""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit

BAZEL_PATH = '/opt/bazel/7.4.1/bazel'
CACHE_ROOT = '/workspace/cache'
REPO_CACHE = CACHE_ROOT + '/bazel_repository'
OUTPUT_BASE = CACHE_ROOT + '/bazel_output'
EXTERNAL = OUTPUT_BASE + '/external'
HEAVY_RAM_MB = '24000'
SKIP_EXTERNAL = ('bazel_tools', 'embedded_tools', 'bazel_tools_embedded')

REQUIRED_TOOLS = ['clang', 'clang++', 'python3', 'patch', 'git']
REQUIRED_PYMODULES = [
    'numpy', 'scipy', 'setuptools', 'wheel', 'build', 'ml_dtypes',
    'opt_einsum', 'zstandard', 'flatbuffers', 'absl', 'typing_extensions',
    'packaging', 'importlib_metadata',
]
FIXED_CPU_WHEELS = [
    'numpy', 'scipy', 'ml_dtypes', 'opt_einsum', 'absl_py', 'typing_extensions',
    'packaging', 'hypothesis', 'pytest', 'setuptools', 'wheel', 'build',
    'rich', 'colorama', 'pygments',
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
    if manifest is None:
        return [f'missing manifest.json in {input_dir}']
    src = manifest.get('source', {})
    filename = src.get('filename')
    if not filename:
        return ['manifest source.filename missing']
    archive = Path(input_dir) / filename
    if not archive.exists():
        return [f'missing source archive: {archive}']
    expected = src.get('sha256')
    if expected and buildkit.digest(archive) != expected:
        return [f'source archive sha256 mismatch: {archive}']
    return []


def _check_tools():
    return [f'missing executable: {t}' for t in REQUIRED_TOOLS if shutil.which(t) is None]


def _check_pymodules():
    return [f'missing python module: {m}' for m in REQUIRED_PYMODULES
            if importlib.util.find_spec(m) is None]


def _check_bazel_prepared():
    problems = []
    if not (Path(BAZEL_PATH).is_file() and os.access(BAZEL_PATH, os.X_OK)):
        problems.append(f'missing bazel 7.4.1 executable: {BAZEL_PATH}')
    for label, path in (('bazel repository cache', REPO_CACHE),
                        ('bazel output_base external tree', EXTERNAL)):
        p = Path(path)
        if not p.is_dir() or not any(p.iterdir()):
            problems.append(f'missing prepared {label}: {path}')
    return problems


def _is_cpu_requirement(name):
    if name in ('jax', 'jaxlib'):
        return False
    return not any(tok in name for tok in ACCELERATOR_TOKENS)


def _parse_requirement_names(text):
    names = set()
    joined = text.replace('\\\r\n', ' ').replace('\\\n', ' ')
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
        if not token or not re_match_name(token):
            continue
        names.add(token.lower().replace('-', '_'))
    return names


def re_match_name(token):
    return all(c.isalnum() or c in '._-' for c in token) and token[0].isalnum()


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
    problems = []
    for pkg in sorted(required):
        if not any(n.startswith(pkg) for n in names):
            problems.append(f'missing CPU wheel in {wh}: {pkg}')
    return problems


def _check_venv():
    tmp = Path('/tmp') / f'bv103_venv_probe_{os.getpid()}'
    try:
        subprocess.run([sys.executable, '-m', 'venv', str(tmp)],
                       check=True, capture_output=True, timeout=180)
        return []
    except Exception as exc:
        return [f'python venv creation failed: {exc}']
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def doctor(input_dir):
    manifest = _read_manifest(input_dir)
    problems = []
    problems += _check_source(input_dir, manifest)
    problems += _check_tools()
    problems += _check_pymodules()
    problems += _check_bazel_prepared()
    filename = (manifest or {}).get('source', {}).get('filename', '')
    archive = Path(input_dir) / filename if filename else None
    if archive is not None and archive.exists():
        problems += _check_wheelhouse(archive)
    else:
        problems.append('cannot check wheelhouse without source archive')
    problems += _check_venv()
    if problems:
        print(json.dumps({'status': 'missing', 'problems': problems}, indent=2))
        return 78
    print(json.dumps({'status': 'ready'}, indent=2))
    return 0


def _repair_external_tree(external):
    """Restore Bazel-written root markers lost when the external tree was exported.

    Bazel materialises an empty ``WORKSPACE`` file at the root of every fetched
    repository; the JAX/XLA build resolves repo roots via
    ``repository_ctx.path(Label("@repo//:WORKSPACE"))``.  When the prepared
    external tree ships without those generated files (and without the matching
    packages) analysis aborts with "BUILD file not found in directory ''".
    Recreate the markers, and drop clearly broken entries so Bazel can
    re-materialise them from the prepared repository cache (still offline).
    """
    external = Path(external)
    actions = []
    if not external.is_dir():
        return ['external tree absent: %s' % external]
    for entry in sorted(external.iterdir()):
        name = entry.name
        if name.startswith('@') or name in SKIP_EXTERNAL:
            continue
        try:
            is_link = entry.is_symlink()
        except OSError:
            continue
        if is_link:
            try:
                entry.resolve(strict=True)
            except OSError:
                try:
                    entry.unlink()
                    (external / ('@' + name + '.marker')).unlink(missing_ok=True)
                    actions.append('removed dangling repository symlink: ' + name)
                except OSError as exc:
                    actions.append('cannot remove %s: %s' % (name, exc))
            continue
        if not entry.is_dir():
            continue
        try:
            empty = not any(entry.iterdir())
        except OSError:
            empty = False
        if empty:
            shutil.rmtree(entry, ignore_errors=True)
            (external / ('@' + name + '.marker')).unlink(missing_ok=True)
            actions.append('removed empty repository directory: ' + name)
            continue
        if (entry / 'WORKSPACE').exists() or (entry / 'WORKSPACE.bazel').exists():
            continue
        try:
            (entry / 'WORKSPACE').write_text('')
            actions.append('restored root WORKSPACE marker: ' + name)
        except OSError as exc:
            actions.append('cannot write WORKSPACE for %s: %s' % (name, exc))
    return actions


def run(args):
    session = buildkit.Session(args.input, args.output, args.jobs)
    session.prepare()
    src = session.src
    out = session.output
    jobs = str(min(session.jobs, 4))

    if not Path(BAZEL_PATH).is_file():
        raise RuntimeError(f'prepared bazel missing: {BAZEL_PATH}')
    for label, path in (('bazel repository cache', REPO_CACHE),
                        ('bazel external tree', EXTERNAL)):
        if not Path(path).is_dir():
            raise RuntimeError(f'prepared {label} missing; run doctor first: {path}')

    actions = _repair_external_tree(EXTERNAL)
    session.write('external_tree_repair.json', {'external': EXTERNAL, 'actions': actions})

    build_env = {
        'JAX_PLATFORMS': 'cpu',
        'JAX_ENABLE_X64': 'true',
        'JAX_NUM_GENERATED_CASES': '1',
        'JAX_RELEASE': '1',
    }

    session.run([
        sys.executable, 'build/build.py', 'build', '--wheels=jaxlib',
        '--python_version=3.12',
        f'--bazel_path={BAZEL_PATH}',
        f'--bazel_startup_options=--output_base={OUTPUT_BASE}',
        f'--bazel_options=--repository_cache={REPO_CACHE}',
        f'--bazel_options=--jobs={jobs}',
        f'--bazel_options=--local_ram_resources={HEAVY_RAM_MB}',
    ], cwd=src, phase='build', name='jaxlib_build', env=build_env, timeout=9000)

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
        env={'JAX_PLATFORMS': 'cpu', 'JAX_ENABLE_X64': 'true',
             'JAX_NUM_GENERATED_CASES': '1'},
        timeout=2400)

    consumer_script = Path(__file__).resolve().parent / 'consumer_check.py'
    session.run([py, str(consumer_script)],
                cwd='/workspace/consumer', phase='consumer', name='functional_consumer',
                env={'JAX_PLATFORMS': 'cpu'}, timeout=600)

    session.finish(features={
        'profile': 'core',
        'scope': 'CPU jaxlib+JAX',
        'bazel': BAZEL_PATH,
        'bazel_repository_cache': REPO_CACHE,
        'bazel_output_base': OUTPUT_BASE,
        'jaxlib_wheel': str(jaxlib_wheel),
        'jax_wheel': str(jax_wheel),
        'official_test': 'lax_numpy_test.py --test_targets=testPad',
        'external_tree_repair': actions,
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
    try:
        run(args)
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
