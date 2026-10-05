#!/usr/bin/env python3
"""BUILDv1-F02: build the TensorFlow v2.18.0 CPU wheel from the frozen source tree.

Subcommands:
  --help                usage only, never touches the source tree or builds
  doctor --input DIR    list exact missing source/tool/dependency items (exit 78) or 0 if ready
  run    --input DIR --output DIR [--jobs N]
                        extract source, configure (CPU only), bazel-build the wheel,
                        run the two frozen official tests, install into a fresh
                        consumer venv and verify SavedModel save/reload

All configure/build/test/install/consumer commands go through buildkit.Session so
argv, exit codes, logs and timing are preserved. Nothing is faked: if the offline
Bazel repository cache or the required wheels are missing the pipeline fails
honestly instead of substituting a prebuilt TensorFlow.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import zipfile
from pathlib import Path

import buildkit

TEST_JOBS = 2
LOCAL_RAM_RESOURCES = 24000
BAZEL_ROOT = Path('/opt/bazel')
REPO_CACHE = Path('/workspace/cache/bazel_repository')
OUTPUT_BASE = Path('/workspace/cache/bazel_output')
WHEELHOUSE = Path('/opt/wheelhouse')
SETUP_PY = 'tensorflow/tools/pip_package/setup.py'
PREBUILT_TF = ('tensorflow', 'tensorflow_cpu', 'tf_nightly', 'tf_nightly_cpu')


def _parse_bazelversion(text):
    """.bazelversion may contain blank/comment lines; return first real line."""
    for line in (text or '').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            return line
    return None


def _peek_tar(archive, relpath):
    """Return text of <top>/relpath inside the frozen archive, no extraction."""
    try:
        with tarfile.open(archive) as tf:
            for member in tf:
                parts = Path(member.name).parts
                if len(parts) >= 2 and '/'.join(parts[1:]) == relpath:
                    fh = tf.extractfile(member)
                    return fh.read().decode('utf-8', 'replace') if fh else None
    except (tarfile.TarError, OSError):
        return None
    return None


def _find_bazel(want):
    if want:
        cand = BAZEL_ROOT / want / 'bazel'
        if cand.is_file():
            return str(cand)
    return shutil.which('bazel') or shutil.which('bazelisk')


def _bazel_version(bazel):
    try:
        out = subprocess.run([bazel, '--version'], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        return 'error: %s' % exc
    lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    return lines[-1] if lines else ''


def _required_packages(setup_text):
    """Read REQUIRED_PACKAGES from the official setup.py template."""
    m = re.search(r'REQUIRED_PACKAGES\s*=\s*\[(.*?)\]', setup_text or '', re.S)
    if not m:
        return []
    names = []
    for raw in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)):
        name = re.split(r'[<>=!~ ]', raw, 1)[0].strip()
        if name:
            names.append(name)
    return names


def _norm(name):
    return name.lower().replace('-', '_').replace('.', '_')


def _wheel_versions(wheelhouse):
    versions = {}
    if not wheelhouse.is_dir():
        return versions
    for f in sorted(wheelhouse.iterdir()):
        if f.suffix != '.whl':
            continue
        parts = f.name[:-4].split('-')
        if len(parts) >= 2:
            versions.setdefault(_norm(parts[0]), parts[1])
    return versions


def _wheel_deps(wheel):
    with zipfile.ZipFile(wheel) as z:
        metas = [n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
        text = z.read(metas[0]).decode('utf-8', 'replace') if metas else ''
    deps = []
    for line in text.splitlines():
        if line.lower().startswith('requires-dist:'):
            name = re.split(r'[<>=!~;\[ ]', line.split(':', 1)[1].strip(), 1)[0].strip()
            if name:
                deps.append(name)
    return deps


def _write_constraints(wheel, dest):
    versions = _wheel_versions(WHEELHOUSE)
    lines = ['%s==%s' % (n, versions[_norm(n)]) for n in _wheel_deps(wheel)
             if _norm(n) in versions]
    dest.write_text('\n'.join(lines) + '\n')
    return len(lines)


def doctor(input_dir):
    input_dir = Path(input_dir)
    report = {'input': str(input_dir), 'missing_source': [], 'missing_tool': [],
              'missing_dependency': [], 'details': {}}
    manifest = archive = None
    want = None
    mp = input_dir / 'manifest.json'
    if not mp.is_file():
        report['missing_source'].append(str(mp))
    else:
        manifest = json.loads(mp.read_text())
        archive = input_dir / manifest['source']['filename']
        if not archive.is_file():
            report['missing_source'].append(str(archive))
        elif buildkit.digest(archive) != manifest['source']['sha256']:
            report['missing_source'].append('checksum mismatch: %s' % archive)
        else:
            report['details']['source_archive'] = {
                'path': str(archive), 'sha256': manifest['source']['sha256']}
            want = _parse_bazelversion(_peek_tar(archive, '.bazelversion') or '')
            report['details']['bazelversion'] = want

    bazel = _find_bazel(want)
    if bazel is None:
        report['missing_tool'].append(
            'bazel %s (expected %s/<version>/bazel)' % (want or 'unknown', BAZEL_ROOT))
    else:
        found = _bazel_version(bazel)
        report['details']['bazel'] = {'path': bazel, 'required': want, 'found': found}
        if want and want not in found:
            report['missing_tool'].append(
                'bazel version mismatch: required %s, found %s' % (want, found))
    for tool in ('gcc', 'clang', 'python3'):
        if shutil.which(tool) is None:
            report['missing_tool'].append(tool)

    declared = manifest.get('dependency_caches') if manifest else None
    report['details']['declared_caches'] = declared if declared else 'none in manifest'
    if not REPO_CACHE.is_dir() or not any(REPO_CACHE.iterdir()):
        report['missing_dependency'].append(
            'Bazel repository cache empty: %s (offline path declared by design)' % REPO_CACHE)
    else:
        report['details']['repository_cache'] = {
            'path': str(REPO_CACHE), 'entries': sum(1 for _ in REPO_CACHE.iterdir())}
    if manifest and manifest.get('offline_dependencies_ready') is False:
        report['missing_dependency'].append(
            'manifest declares offline_dependencies_ready=false: vendored Bazel '
            'external repos (llvm, eigen, pybind11, rules_python ...) not sealed')

    reqs = _required_packages(_peek_tar(archive, SETUP_PY) if archive else '')
    report['details']['required_packages'] = reqs
    versions = _wheel_versions(WHEELHOUSE)
    if not WHEELHOUSE.is_dir():
        report['missing_dependency'].append('%s (offline Python wheels)' % WHEELHOUSE)
    else:
        missing = [r for r in reqs if _norm(r) not in versions]
        if missing:
            report['missing_dependency'].append(
                'wheels absent from %s for required packages: %s'
                % (WHEELHOUSE, ', '.join(missing)))
    for bad in PREBUILT_TF:
        if bad in versions:
            report['missing_dependency'].append(
                'prebuilt %s wheel present in %s; consumer must use only the newly '
                'built wheel' % (bad, WHEELHOUSE))

    report['ready'] = not (report['missing_source'] or report['missing_tool']
                           or report['missing_dependency'])
    print(json.dumps(report, indent=2))
    return 0 if report['ready'] else 78


def _configure_env(path_dir):
    env = {
        'TF_NEED_CUDA': '0', 'TF_NEED_ROCM': '0', 'TF_NEED_TENSORRT': '0',
        'TF_NEED_OPENCL_SYCL': '0', 'TF_NEED_MPI': '0', 'TF_CUDA_CLANG': '0',
        'TF_MKL_BUILD': '0', 'TF_CUDA_COMPUTE_CAPABILITIES': '',
        'TF_DOWNLOAD_CLANG': '0', 'TF_NEED_CLANG': '0',
        'TF_SET_ANDROID_WORKSPACE': '0', 'CC_OPT_FLAGS': '-Wno-sign-compare',
        'PYTHON_BIN_PATH': sys.executable,
        'PYTHON_LIB_PATH': sysconfig.get_paths().get('purelib', ''),
    }
    if path_dir:
        env['PATH'] = path_dir + os.pathsep + os.environ.get('PATH', '')
    return env


def run(input_dir, output_dir, jobs):
    session = buildkit.Session(input_dir, output_dir, jobs=min(int(jobs), 4))
    src = session.prepare()
    python_bin = sys.executable

    want = _parse_bazelversion((src / '.bazelversion').read_text(errors='replace'))
    bazel = _find_bazel(want)
    if bazel is None:
        raise RuntimeError('bazel %s not found under %s (see doctor)' % (want, BAZEL_ROOT))
    bazel_dir = str(Path(bazel).parent)
    if not REPO_CACHE.is_dir() or not any(REPO_CACHE.iterdir()):
        raise RuntimeError('offline Bazel repository cache %s is missing (see doctor)' % REPO_CACHE)
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

    session.run([python_bin, './configure'], cwd=src, phase='configure', name='configure',
                env=_configure_env(bazel_dir), timeout=1800)

    build = [bazel, '--output_base=%s' % OUTPUT_BASE, 'build',
             '--repository_cache=%s' % REPO_CACHE,
             '--jobs=%d' % session.jobs,
             '--local_ram_resources=%d' % LOCAL_RAM_RESOURCES,
             '--repo_env=USE_PYWRAP_RULES=1',
             '--repo_env=WHEEL_NAME=tensorflow_cpu',
             '--config=opt',
             '//tensorflow/tools/pip_package:wheel']
    session.run(build, cwd=src, phase='build', name='bazel_build_wheel', timeout=10800)

    wheel_house = src / 'bazel-bin' / 'tensorflow' / 'tools' / 'pip_package' / 'wheel_house'
    wheels = sorted(wheel_house.glob('tensorflow_cpu-*.whl'))
    if not wheels:
        raise RuntimeError('bazel build finished but no tensorflow_cpu wheel in %s' % wheel_house)
    wheel = wheels[-1]
    shutil.copy2(wheel, session.output / wheel.name)
    session.run([python_bin, '-m', 'pip', 'install', '--no-index', '--no-deps',
                 '--target', str(session.install), str(wheel)],
                cwd=session.output, phase='package', name='install_wheel', timeout=1800)

    common = [bazel, '--output_base=%s' % OUTPUT_BASE, 'test',
              '--repository_cache=%s' % REPO_CACHE,
              '--config=linux', '--test_output=all',
              '--jobs=%d' % TEST_JOBS, '--local_test_jobs=%d' % TEST_JOBS,
              '--cache_test_results=no', '--test_timeout=1800']
    session.test('softmax_op_test',
                 common + ['//tensorflow/python/kernel_tests/nn_ops:softmax_op_test'],
                 cwd=src, timeout=3600)
    session.test('load_test.test_capture_variables',
                 common + ['--test_filter=*LoadTest.test_capture_variables*',
                           '//tensorflow/python/saved_model:load_test'],
                 cwd=src, timeout=3600)

    consumer = Path('/workspace/consumer')
    consumer.mkdir(parents=True, exist_ok=True)
    venv = consumer / 'venv'
    if venv.exists():
        shutil.rmtree(venv)
    session.run([python_bin, '-m', 'venv', str(venv)], cwd=consumer, phase='install',
                name='create_consumer_venv', timeout=900)
    vpy = venv / 'bin' / 'python'
    constraints = consumer / 'constraints.txt'
    pinned = _write_constraints(wheel, constraints)
    session.write('consumer_constraints.txt', constraints.read_text().splitlines())
    session.run([str(vpy), '-m', 'pip', 'install', '--no-index',
                 '--find-links=%s' % WHEELHOUSE, '--constraints=%s' % constraints,
                 str(wheel)],
                cwd=consumer, phase='install', name='install_consumer', timeout=1800)

    script = Path(__file__).resolve().parent / 'consumer_check.py'
    saved = consumer / 'saved_model'
    if saved.exists():
        shutil.rmtree(saved)
    session.run([str(vpy), str(script), 'info'], cwd=consumer, phase='consumer',
                name='consumer_info', timeout=900)
    session.run([str(vpy), str(script), 'save', str(saved)], cwd=consumer,
                phase='consumer', name='consumer_save', timeout=900)
    session.run([str(vpy), str(script), 'load', str(saved)], cwd=consumer,
                phase='consumer', name='consumer_load', timeout=900)

    session.finish(features={
        'wheel': wheel.name, 'wheel_sha256': buildkit.digest(wheel),
        'python': '%d.%d' % sys.version_info[:2], 'device': 'cpu',
        'cuda': False, 'rocm': False, 'build_jobs': session.jobs,
        'test_jobs': TEST_JOBS, 'pinned_dependencies': pinned,
        'bazel': bazel, 'repository_cache': str(REPO_CACHE),
        'output_base': str(OUTPUT_BASE),
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='main.py',
        description='Build the TensorFlow v2.18.0 CPU wheel from frozen source.')
    sub = parser.add_subparsers(dest='command')
    d = sub.add_parser('doctor', help='report missing source/tool/dependency items')
    d.add_argument('--input', required=True)
    r = sub.add_parser('run', help='extract, build, test, package and verify')
    r.add_argument('--input', required=True)
    r.add_argument('--output', required=True)
    r.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == 'doctor':
        return doctor(args.input)
    if args.command == 'run':
        return run(args.input, args.output, min(args.jobs, 4))
    parser.error('unknown command')
    return 2


if __name__ == '__main__':
    sys.exit(main())
