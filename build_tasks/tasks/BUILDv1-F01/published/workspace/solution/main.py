#!/usr/bin/env python3
"""BUILDv1-F01: build a CPU PyTorch wheel from the pinned complete source
archive, install it into an isolated consumer venv outside src, run the frozen
official Linear selection, and verify a small C++ extension consumer.

The source archive is treated as the genuine, complete upstream tree. Nothing
is synthesized, stubbed or patched: no placeholder licenses, no fallback
module directories, no edits to upstream build or test files.

One genuine provisioned dependency is required: the pin's
``tools/build_pytorch_libs.py`` calls ``checkout_nccl()`` unconditionally even
with ``USE_CUDA=0``/``USE_NCCL=0``. The manifest supplies the exact official
NVIDIA/nccl source as an offline dependency cache; after ``prepare()`` its
genuine source tree is copied into ``third_party/nccl`` so the real existence
check is satisfied without networking, fake ``.git`` data, empty folders or
source patches. No NCCL/GPU target is compiled (CPU flags unchanged).
"""
import argparse
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

import buildkit

WHEELHOUSE = Path('/opt/wheelhouse')
NCCL_CACHE = Path('/workspace/cache/torch_nccl')
NCCL_TARBALLS = [
    Path('/workspace/cache/torch_nccl/torch-nccl-source.tar.gz'),
    Path('/workspace/cache/torch-nccl-source.tar.gz'),
]

# pytest is pinned: pytest>=9 removes the legacy ``path`` argument from
# ``pytest_pycollect_makemodule``, which the genuine upstream test/conftest.py
# still uses. pytest 8.3.5 is present in the provisioned wheelhouse and collects
# the real test/test_nn.py -k Linear selection successfully.
PYTEST_PIN = 'pytest==8.3.5'

BUILD_REQUIREMENTS = [
    'setuptools', 'wheel', 'numpy', 'pyyaml', 'typing-extensions',
    'requests', 'astunparse', 'ninja', 'cmake', 'build', 'packaging',
    'pyproject-hooks', 'filelock', 'sympy', 'networkx', 'jinja2',
    'fsspec', 'mpmath', PYTEST_PIN,
]

CONSUMER_TEST_DEPS = [
    PYTEST_PIN, 'expecttest', 'hypothesis', 'numpy', 'packaging',
    'filelock', 'sympy', 'networkx', 'jinja2', 'fsspec', 'mpmath',
    'typing-extensions', 'pyyaml', 'psutil',
]

REQUIRED_TOOLS = ['gcc', 'g++', 'cmake', 'ninja', 'make', 'git']


def build_env(jobs):
    """CPU-only configuration; distributed and unneeded CPU accel backends off."""
    return {
        'USE_CUDA': '0', 'USE_ROCM': '0', 'USE_XPU': '0',
        'USE_DISTRIBUTED': '0', 'USE_GLOO': '0', 'USE_MPI': '0',
        'USE_TENSORPIPE': '0', 'USE_NCCL': '0', 'USE_SYSTEM_NCCL': '0',
        'USE_MAGMA': '0', 'USE_CUDNN': '0', 'USE_CUSPARSELT': '0',
        'USE_CUDSS': '0', 'USE_CUFILE': '0',
        'USE_NNPACK': '0', 'USE_QNNPACK': '0', 'USE_XNNPACK': '0',
        'USE_FBGEMM': '0', 'USE_KINETO': '0', 'USE_ONNX': '0',
        'USE_NUMA': '0', 'USE_ITT': '0', 'USE_MKLDNN': '0',
        'USE_OPENMP': '1', 'USE_MIMALLOC': '1',
        'USE_OPENCL': '0', 'USE_VULKAN': '0',
        'USE_NATIVE_ARCH': '0', 'BUILD_TEST': '0', 'BUILD_BINARY': '0',
        'BUILD_SHARED_LIBS': 'ON', '_GLIBCXX_USE_CXX11_ABI': '0',
        'MAX_JOBS': str(jobs), 'CMAKE_BUILD_PARALLEL_LEVEL': str(jobs),
        'PYTHONPATH': '', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
        'PIP_NO_INPUT': '1', 'BUILD_PYTHON': '1',
    }


def _looks_like_nccl(d):
    return d.is_dir() and (d / 'src').is_dir() and (
        (d / 'CMakeLists.txt').is_file() or (d / 'Makefile').is_file())


def _locate_nccl_root(tree):
    if _looks_like_nccl(tree):
        return tree
    for p in sorted(tree.rglob('*')):
        if _looks_like_nccl(p):
            return p
    return None


def _extract_archive(archive, dest):
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            parts = Path(member.name).parts
            if not parts or '..' in parts or Path(member.name).is_absolute():
                raise RuntimeError('unsafe archive member: ' + member.name)
        tf.extractall(dest, filter='data')


def _nccl_candidates():
    trees = []
    if NCCL_CACHE.exists():
        if NCCL_CACHE.is_dir():
            for arc in (sorted(NCCL_CACHE.glob('*.tar.gz')) +
                        sorted(NCCL_CACHE.glob('*.tgz'))):
                tmp = Path(tempfile.mkdtemp(prefix='nccl-', dir='/tmp'))
                _extract_archive(arc, tmp)
                trees.append(tmp)
            trees.append(NCCL_CACHE)
        else:
            tmp = Path(tempfile.mkdtemp(prefix='nccl-', dir='/tmp'))
            _extract_archive(NCCL_CACHE, tmp)
            trees.append(tmp)
    for arc in NCCL_TARBALLS:
        if arc.is_file():
            tmp = Path(tempfile.mkdtemp(prefix='nccl-', dir='/tmp'))
            _extract_archive(arc, tmp)
            trees.append(tmp)
    return trees


def nccl_cache_available():
    if NCCL_CACHE.exists():
        if NCCL_CACHE.is_dir() and _locate_nccl_root(NCCL_CACHE) is not None:
            return True
        if NCCL_CACHE.is_file():
            return True
        if NCCL_CACHE.is_dir() and any(NCCL_CACHE.glob('*.tar.gz')):
            return True
    return any(arc.is_file() for arc in NCCL_TARBALLS)


def populate_nccl_source(src):
    """Place the genuine provisioned NCCL source at third_party/nccl."""
    dest = src / 'third_party' / 'nccl'
    if _looks_like_nccl(dest):
        return 'present'
    if dest.exists():
        if dest.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
        else:
            dest.unlink()
    for tree in _nccl_candidates():
        root = _locate_nccl_root(tree)
        if root is not None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(root, dest, symlinks=True)
            return 'copied:' + str(root)
    raise RuntimeError(
        'genuine NCCL source not found in provisioned cache ' + str(NCCL_CACHE))


def run_cmd(args):
    sess = buildkit.Session(args.input, args.output, args.jobs)
    sess.prepare()
    src = sess.src
    env = build_env(sess.jobs)

    nccl_action = populate_nccl_source(src)
    sess.write('nccl_provision.json', {'action': nccl_action,
                                       'destination': str(src / 'third_party' / 'nccl')})

    build_venv = Path('/workspace/build/venv')
    sess.run([sys.executable, '-m', 'venv', str(build_venv)],
             phase='venv_build', name='venv_build', cwd=sess.build, env=env)
    bpy = str(build_venv / 'bin' / 'python')
    sess.run([bpy, '-m', 'pip', 'install', '--no-index',
              '--find-links', str(WHEELHOUSE), '--upgrade'] + BUILD_REQUIREMENTS,
             phase='build_deps', name='build_deps', cwd=sess.build, env=env,
             timeout=2400)

    sess.run([bpy, '-m', 'build', '--wheel', '--no-isolation',
              '--outdir', str(sess.output), str(src)],
             phase='build', name='wheel', cwd=src, env=env, timeout=9000)

    wheels = sorted(sess.output.glob('torch-*.whl'))
    if not wheels:
        raise RuntimeError('build produced no torch-*.whl')
    wheel = wheels[-1]
    shutil.copy2(wheel, sess.install / wheel.name)
    sess.write('wheel_sha256.json',
               {'wheel': wheel.name, 'sha256': buildkit.digest(wheel),
                'bytes': wheel.stat().st_size})

    cons_venv = sess.consumer / 'venv'
    sess.run([sys.executable, '-m', 'venv', str(cons_venv)],
             phase='venv_consumer', name='venv_consumer', cwd=sess.consumer,
             env=env)
    cpy = str(cons_venv / 'bin' / 'python')
    sess.run([cpy, '-m', 'pip', 'install', '--no-index',
              '--find-links', str(WHEELHOUSE), str(wheel)],
             phase='install_wheel', name='install_wheel', cwd=sess.consumer,
             env=env, timeout=2400)
    sess.run([cpy, '-m', 'pip', 'install', '--no-index',
              '--find-links', str(WHEELHOUSE)] + CONSUMER_TEST_DEPS,
             phase='install_test_deps', name='install_test_deps',
             cwd=sess.consumer, env=env, timeout=2400)

    # Sanity assertion: the freshly installed wheel, not the checkout tree,
    # must win the import in the consumer venv without any PYTHONPATH hints.
    sess.run([cpy, '-c',
              'import torch,sys; print("torch_file="+torch.__file__); '
              'assert sys.prefix in torch.__file__, torch.__file__'],
             phase='verify_torch_resolution', name='verify_torch_resolution',
             cwd=sess.consumer, env=env)

    # Official pytest selection.
    #
    # test/conftest.py at line 21 does ``import pytest_shard_custom``, a genuine
    # upstream helper located at test/pytest_shard_custom.py.  With
    # ``--import-mode=importlib`` pytest no longer prepends each test directory
    # to sys.path, so that helper must be reachable via PYTHONPATH.
    #
    # PYTHONPATH is set to ONLY the test directory (/workspace/src/test), never
    # the source root: the helper resolves, while the freshly installed wheel
    # still owns the ``torch`` import so unbuilt checkout code cannot shadow it.
    # The pre-test guard asserts ``sys.prefix`` is inside ``torch.__file__``
    # under exactly this environment before the selector runs.
    test_env = {
        'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2',
        'OPENBLAS_NUM_THREADS': '2',
        'PYTHONPATH': str(src / 'test'),
        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
        'TORCH_EXTENSIONS_DIR': str(sess.consumer / 'torch_ext'),
        'TORCH_HOME': str(sess.consumer / 'torch_home'),
    }
    sess.test('test_nn_Linear_import_guard',
              [cpy, '-c',
               'import torch,sys; print("torch_file="+torch.__file__); '
               'assert sys.prefix in torch.__file__, torch.__file__; '
               'import pytest_shard_custom; '
               'print("helper="+pytest_shard_custom.__file__)'],
              cwd=sess.consumer, env=test_env, timeout=120)

    sess.test('test_nn_Linear_selection',
              [cpy, '-m', 'pytest', str(src / 'test' / 'test_nn.py'),
               '-k', 'Linear', '--import-mode=importlib',
               '-p', 'no:cacheprovider', '-q'],
              cwd=sess.consumer, env=test_env, timeout=7200)

    sol = Path(__file__).resolve().parent
    cenv = {
        'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2',
        'OPENBLAS_NUM_THREADS': '2', 'PYTHONPATH': '',
        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
        'TORCH_EXTENSIONS_DIR': str(sess.consumer / 'torch_ext'),
        'TORCH_HOME': str(sess.consumer / 'torch_home'),
    }
    sess.run([cpy, str(sol / 'consumer_verify.py'), str(cons_venv)],
             phase='consumer_verify', name='consumer_verify',
             cwd=sess.consumer, env=cenv)
    sess.run([cpy, str(sol / 'consumer_ext.py'), str(sess.consumer / 'ext_build')],
             phase='consumer_ext', name='consumer_ext',
             cwd=sess.consumer, env=cenv, timeout=1800)

    sess.finish(features={
        'profile': 'core', 'cpu_only': True, 'distributed': False,
        'wheel': wheel.name, 'official_test': 'test/test_nn.py -k Linear',
        'pytest_pin': PYTEST_PIN,
        'consumer': 'isolated venv + cpp_extension consumer',
        'source_unmodified': True,
        'nccl_provision': nccl_action,
        'test_pythonpath': str(src / 'test'),
        'backends_disabled': ['cuda', 'rocm', 'xpu', 'distributed', 'nnpack',
                              'qnnpack', 'xnnpack', 'fbgemm', 'kineto',
                              'mkldnn', 'nccl', 'magma', 'onnx', 'gloo'],
    })
    return 0


def doctor(input_dir):
    msgs = []
    mpath = Path(input_dir) / 'manifest.json'
    m = {}
    if not mpath.is_file():
        msgs.append('MISSING manifest.json at ' + str(mpath))
    else:
        try:
            m = json.loads(mpath.read_text())
        except Exception as exc:
            msgs.append('INVALID manifest.json: ' + str(exc))
    src_info = m.get('source') or {}
    archive = Path(input_dir) / src_info.get('filename',
                                             'source-all-submodules.tar.gz')
    if not archive.is_file():
        msgs.append('MISSING source archive: ' + str(archive))
    elif src_info.get('sha256'):
        try:
            if buildkit.digest(archive) != src_info['sha256']:
                msgs.append('CHECKSUM MISMATCH: ' + str(archive))
        except Exception as exc:
            msgs.append('CANNOT HASH ' + str(archive) + ': ' + str(exc))
    if not nccl_cache_available():
        msgs.append('MISSING NCCL source cache: ' + str(NCCL_CACHE))
    for tool in REQUIRED_TOOLS:
        if not shutil.which(tool):
            msgs.append('MISSING tool: ' + tool)
    if not WHEELHOUSE.is_dir():
        msgs.append('MISSING wheelhouse: ' + str(WHEELHOUSE))
    else:
        names = [p.name.lower().replace('_', '-')
                 for p in WHEELHOUSE.glob('*.whl')]
        needed = set(BUILD_REQUIREMENTS) | set(CONSUMER_TEST_DEPS)
        # pytest==8.3.5 is required; any other pytest version is not sufficient.
        if not any(n.startswith('pytest-8.3.5-') for n in names):
            msgs.append('MISSING wheel in ' + str(WHEELHOUSE) +
                        ': pytest==8.3.5 (required for upstream conftest)')
        needed.discard(PYTEST_PIN)
        for pkg in sorted(needed):
            key = pkg.lower().replace('_', '-') + '-'
            if not any(n.startswith(key) for n in names):
                msgs.append('MISSING wheel in ' + str(WHEELHOUSE) + ': ' + pkg)
    if sys.version_info < (3, 9):
        msgs.append('UNSUPPORTED python ' + sys.version.split()[0] + ' (<3.9)')
    if msgs:
        print('doctor: NOT READY')
        for line in msgs:
            print('  - ' + line)
        return 78
    print('doctor: READY')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='main.py',
        description='Build a CPU PyTorch wheel from the pinned complete source, '
                    'install it into an isolated consumer venv and run the '
                    'frozen official Linear selection.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    rp = sub.add_parser('run', help='build, install, test and verify')
    rp.add_argument('--input', required=True)
    rp.add_argument('--output', required=True)
    rp.add_argument('--jobs', type=int, default=4)
    dp = sub.add_parser('doctor', help='report missing source/tool/dependency items')
    dp.add_argument('--input', required=True)
    args = ap.parse_args(argv)
    if args.cmd == 'run':
        return run_cmd(args)
    if args.cmd == 'doctor':
        return doctor(args.input)
    return 2


if __name__ == '__main__':
    sys.exit(main())
