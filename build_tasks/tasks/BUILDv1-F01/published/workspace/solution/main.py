#!/usr/bin/env python3
"""BUILDv1-F01: build a CPU PyTorch wheel from source, install it into an
isolated consumer venv outside src, run the official Linear selection, and
verify a small C++ extension consumer."""
import argparse
import json
import shutil
import sys
from pathlib import Path

import buildkit

WHEELHOUSE = Path('/opt/wheelhouse')

BUILD_REQUIREMENTS = [
    'setuptools', 'wheel', 'numpy', 'pyyaml', 'typing-extensions',
    'requests', 'astunparse', 'ninja', 'cmake', 'build', 'packaging',
    'pyproject-hooks', 'filelock', 'sympy', 'networkx', 'jinja2',
    'fsspec', 'mpmath', 'expecttest', 'pytest', 'hypothesis',
]

CONSUMER_TEST_DEPS = [
    'pytest', 'expecttest', 'hypothesis', 'numpy', 'packaging',
    'filelock', 'sympy', 'networkx', 'jinja2', 'fsspec', 'mpmath',
    'typing-extensions', 'pyyaml',
]

REQUIRED_TOOLS = ['gcc', 'g++', 'cmake', 'ninja', 'make']

SUBMODULE_MARKERS = ('CMakeLists.txt', 'Makefile', 'setup.py',
                     'LICENSE', 'LICENSE.md', 'LICENSE.txt')

FALLBACK_STUBS = (
    'third_party/gloo',
    'third_party/cutlass',
    'third_party/cudnn_frontend',
    'third_party/nccl',
    'third_party/QNNPACK',
    'third_party/breakpad',
    'third_party/ios-cmake',
    'third_party/asmjit',
    'third_party/tbb',
)


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


def ensure_submodule_stubs(src):
    """The vendored archive ships only the submodules the frozen CORE CPU
    profile actually compiles. PyTorch's setup.py nevertheless verifies that
    every expected submodule directory contains a recognizable file, even for
    backends that are disabled via environment variables. Provide inert
    placeholders for the omitted (disabled-backend) submodules so the check
    passes and those backends are simply not built or linked."""
    candidates = []
    gm = src / '.gitmodules'
    if gm.is_file():
        for line in gm.read_text(errors='replace').splitlines():
            s = line.strip()
            if s.startswith('path'):
                parts = s.split('=', 1)
                if len(parts) == 2 and parts[1].strip():
                    candidates.append(parts[1].strip())
    for extra in FALLBACK_STUBS:
        if extra not in candidates:
            candidates.append(extra)

    stubbed = []
    for rel in candidates:
        d = src / rel
        if d.is_dir() and any((d / f).exists() for f in SUBMODULE_MARKERS):
            continue
        d.mkdir(parents=True, exist_ok=True)
        (d / 'LICENSE').write_text(
            'Placeholder for a submodule not vendored because the module that '
            'depends on it is disabled in this build profile.')
        (d / 'CMakeLists.txt').write_text(
            '# placeholder; dependent backend disabled in this build profile')
        stubbed.append(rel)
    return stubbed


def run_cmd(args):
    sess = buildkit.Session(args.input, args.output, args.jobs)
    sess.prepare()
    src = sess.src
    env = build_env(sess.jobs)

    stubs = ensure_submodule_stubs(src)
    sess.write('submodule_stubs.json', stubs)

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
             phase='build_wheel', name='wheel', cwd=src, env=env, timeout=7200)

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
             phase='venv_consumer', name='venv_consumer', cwd=sess.consumer, env=env)
    cpy = str(cons_venv / 'bin' / 'python')
    sess.run([cpy, '-m', 'pip', 'install', '--no-index',
              '--find-links', str(WHEELHOUSE), str(wheel)],
             phase='install_wheel', name='install_wheel', cwd=sess.consumer,
             env=env, timeout=2400)
    sess.run([cpy, '-m', 'pip', 'install', '--no-index',
              '--find-links', str(WHEELHOUSE)] + CONSUMER_TEST_DEPS,
             phase='install_test_deps', name='install_test_deps',
             cwd=sess.consumer, env=env, timeout=2400)

    cenv = {
        'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2',
        'PYTHONPATH': '', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
        'TORCH_EXTENSIONS_DIR': str(sess.consumer / 'torch_ext'),
        'TORCH_HOME': str(sess.consumer / 'torch_home'),
    }

    sess.test('test_nn_Linear',
              [cpy, '-m', 'pytest', str(src / 'test' / 'test_nn.py'),
               '-k', 'Linear', '--import-mode=importlib',
               '-p', 'no:cacheprovider', '-q'],
              cwd=sess.consumer, env=cenv, timeout=7200)

    sol = Path(__file__).resolve().parent
    sess.run([cpy, str(sol / 'consumer_verify.py'), str(cons_venv)],
             phase='consumer_verify', name='consumer_verify',
             cwd=sess.consumer, env=cenv)
    sess.run([cpy, str(sol / 'consumer_ext.py'), str(sess.consumer / 'ext_build')],
             phase='consumer_ext', name='consumer_ext',
             cwd=sess.consumer, env=cenv, timeout=1800)

    sess.finish(features={
        'profile': 'core', 'cpu_only': True, 'distributed': False,
        'wheel': wheel.name, 'official_test': 'test/test_nn.py -k Linear',
        'consumer': 'isolated venv + cpp_extension consumer',
        'submodule_stubs': stubs,
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
    archive = Path(input_dir) / src_info.get('filename', 'source-with-submodules.tar.gz')
    if not archive.is_file():
        msgs.append('MISSING source archive: ' + str(archive))
    elif src_info.get('sha256'):
        try:
            if buildkit.digest(archive) != src_info['sha256']:
                msgs.append('CHECKSUM MISMATCH: ' + str(archive))
        except Exception as exc:
            msgs.append('CANNOT HASH ' + str(archive) + ': ' + str(exc))
    for tool in REQUIRED_TOOLS:
        if not shutil.which(tool):
            msgs.append('MISSING tool: ' + tool)
    if not WHEELHOUSE.is_dir():
        msgs.append('MISSING wheelhouse: ' + str(WHEELHOUSE))
    else:
        names = [p.name.lower().replace('_', '-') for p in WHEELHOUSE.glob('*.whl')]
        needed = set(BUILD_REQUIREMENTS) | set(CONSUMER_TEST_DEPS)
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
        description='Build a CPU PyTorch wheel from source, install it into an '
                    'isolated consumer venv and run the official Linear selection.')
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
