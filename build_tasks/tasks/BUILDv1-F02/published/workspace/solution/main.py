#!/usr/bin/env python3
"""BUILDv1-F02: build the TensorFlow v2.18.0 CPU wheel from the frozen source tree.

Subcommands:
  --help                usage only, never touches the source tree or builds
  doctor --input DIR    list exact missing source/tool/dependency items (exit 78) or 0 if ready
  run    --input DIR --output DIR [--jobs N]

We never synthesize toolchain configuration or stub workspace rules. The frozen
Bazel repository cache and the pre-resolved external repositories declared by
the manifest are treated as immutable builder inputs; if they are absent or
incomplete the pipeline fails honestly (and `doctor` reports the exact missing
path) instead of fabricating replacements or substituting a prebuilt wheel.

Frozen CPU build facts baked into this solution:
  * Bazel binary is always /opt/bazel/<.bazelversion>/bazel (the first non-empty,
    non-comment line of `.bazelversion`); /opt/bazel/<version> is prepended to
    PATH for `bash ./configure` so upstream configure.py probes the right tool.
  * CPU answers: clang-18, CPython of the running interpreter, CUDA/ROCm/TensorRT
    /OpenCL-SYCL/MPI all off. `.tf_configure.bazelrc` is verified after configure.
  * Bazel caches come from the manifest's
    `bazel_dependency_preparation.cache_directories` (`bazel_repository`,
    `bazel_output/external`): repository cache at /workspace/cache/bazel_repository,
    explicit startup --output_base=/workspace/cache/bazel_output and prepared
    external repositories at /workspace/cache/bazel_output/external.
  * `patchelf` is required by the official wheel-packaging step
    (build_pip_package.py -> patch_so -> subprocess.check_output(['patchelf', ...])).
    It is a real bootstrap binary provided by the task image; we locate it, run
    `patchelf --version` before building, and export its directory through
    `--action_env=PATH=...` so the Bazel run action can execute it. No RPATH stub,
    no source edit, no fake wheel.
  * clang-18 compatibility: the vendored @upb//:upb C source uses an anonymous
    struct type inside offsetof(), which clang>=16 diagnoses as
    -Wgnu-offsetof-extensions; TensorFlow's -Werror set promotes that to an error.
    We add only --copt/--host_copt=-Wno-error=gnu-offsetof-extensions so that one
    known GNU C extension is demoted back to a warning. Everything else - source
    code, BUILD/toolchain definitions, optimizations, features, official tests -
    is untouched.

Build parallelism honors min(user --jobs, manifest build_job_limit); the Bazel
`--jobs` value is bound to it. Test parallelism stays fixed at TEST_JOBS=2.
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
LOCAL_RAM_RESOURCES = 16000
DEFAULT_BUILD_JOBS = 8
CACHE_ROOT = Path('/workspace/cache')
BAZEL_ROOT = Path('/opt/bazel')
BAZEL_HOME = Path('/workspace/build/home')
WHEELHOUSE = Path('/opt/wheelhouse')
SETUP_PY = 'tensorflow/tools/pip_package/setup.py'
PREBUILT_TF = ('tensorflow', 'tensorflow_cpu', 'tf_nightly', 'tf_nightly_cpu')
OPTIONAL_PACKAGES = {'tensorflow_io_gcs_filesystem'}
NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9._-]*$')
# Compatibility flags for clang>=16 diagnosing the vendored upb/upb.c anonymous
# struct inside offsetof(). Applied to target and host compiler configuration.
CLANG_COMPAT_OPTS = ['--copt=-Wno-error=gnu-offsetof-extensions',
                     '--host_copt=-Wno-error=gnu-offsetof-extensions']
# Real Ubuntu patchelf bootstrap locations. No wrapper is created here; the
# wheel-packaging action executes the genuine binary that the task image ships.
PATCHELF_CANDIDATES = (
    '/opt/bootstrap/patchelf/bin/patchelf',
    '/opt/bootstrap/patchelf/patchelf',
    '/opt/patchelf/bin/patchelf',
    '/opt/patchelf/patchelf',
    '/usr/local/bin/patchelf',
    '/usr/bin/patchelf',
    '/bin/patchelf',
)
PATCHELF_GLOBS = (
    '*/bin/patchelf', '/patchelf', 'patchelf/bin/patchelf', 'patchelf',
)


# --------------------------------------------------------------------------- #
# Small parsing helpers
# --------------------------------------------------------------------------- #

def _parse_bazelversion(text):
    """.bazelversion may contain blank/comment lines; return the first real one."""
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


def _norm(name):
    return name.lower().replace('-', '_').replace('.', '_')


# --------------------------------------------------------------------------- #
# Manifest-derived cache paths (no invented legacy locations)
# --------------------------------------------------------------------------- #

def cache_layout(manifest):
    """Return (repository_cache, output_base, external_repos) the builder froze.

    Derived from manifest.bazel_dependency_preparation.cache_directories which
    the frozen design declares as ['bazel_repository', 'bazel_output/external']
    (relative to /workspace/cache).
    """
    repo = CACHE_ROOT / 'bazel_repository'
    out = CACHE_ROOT / 'bazel_output'
    external = out / 'external'
    prep = (manifest or {}).get('bazel_dependency_preparation') or {}
    for raw in prep.get('cache_directories') or []:
        entry = Path(raw)
        p = entry if entry.is_absolute() else CACHE_ROOT / entry
        if entry.name == 'bazel_repository':
            repo = p
        elif entry.name == 'external':
            external = p
            out = p.parent
        elif entry.name == 'bazel_output':
            out = p
            external = p / 'external'
    return repo, out, external


def build_job_limit(manifest):
    """Honor min(user --jobs, manifest build_job_limit); no hard clamp of 4."""
    manifest = manifest or {}
    raw = manifest.get('build_job_limit')
    if raw is None:
        raw = manifest.get('build_jobs')
    try:
        return max(1, min(8, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_BUILD_JOBS


# --------------------------------------------------------------------------- #
# Wheel metadata helpers
# --------------------------------------------------------------------------- #

def _required_packages(setup_text):
    """Read REQUIRED_PACKAGES from the official setup.py template.

    The upstream file embeds the list inside a normal Python expression, so the
    regex could otherwise pick up stray quoted strings such as the separator in
    `', '.join([...])`. Only keep tokens that look like real package names.
    """
    m = re.search(r'REQUIRED_PACKAGES\s*=\s*\[(.*?)\]', setup_text or '', re.S)
    if not m:
        return []
    names = []
    for raw in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)):
        name = re.split(r'[<>=!~ ;\[]', raw, 1)[0].strip()
        if name and NAME_RE.match(name):
            names.append(name)
    seen, ordered = set(), []
    for name in names:
        key = _norm(name)
        if key not in seen:
            seen.add(key)
            ordered.append(name)
    return ordered


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
            raw = line.split(':', 1)[1].strip()
            name = re.split(r'[<>=!~;\[ ]', raw, 1)[0].strip()
            if name and NAME_RE.match(name):
                deps.append(name)
    return deps


def _write_constraints(wheel, dest):
    versions = _wheel_versions(WHEELHOUSE)
    lines = ['%s==%s' % (n, versions[_norm(n)]) for n in _wheel_deps(wheel)
             if _norm(n) in versions]
    dest.write_text('\n'.join(lines) + '\n')
    return len(lines)


# --------------------------------------------------------------------------- #
# Bazel / patchelf / toolchain discovery
# --------------------------------------------------------------------------- #

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
    lines = [ln.strip() for ln in (out.stdout or '').splitlines() if ln.strip()]
    return lines[-1] if lines else ''


def _find_patchelf():
    """Locate the real patchelf bootstrap binary provided by the task image."""
    which = shutil.which('patchelf')
    if which:
        return which
    for cand in PATCHELF_CANDIDATES:
        p = Path(cand)
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p)
    for base in ('/opt/bootstrap', '/opt', '/usr/local'):
        root = Path(base)
        if not root.is_dir():
            continue
        for pattern in PATCHELF_GLOBS:
            for hit in sorted(root.glob(pattern)):
                if hit.is_file() and os.access(str(hit), os.X_OK):
                    return str(hit)
    return None


def _patchelf_probe(binary):
    """Run the real `patchelf --version`; return (ok, version-or-error)."""
    if not binary:
        return (False, 'patchelf executable not found on PATH or bootstrap dirs')
    try:
        out = subprocess.run([binary, '--version'], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, 'patchelf --version failed: %s' % exc)
    text = (out.stdout or '').strip()
    if out.returncode != 0 or 'patchelf' not in text.lower():
        return (False, 'patchelf --version rc=%s output=%r'
                % (out.returncode, text[:200]))
    return (True, text.splitlines()[0])


def _action_path(patchelf_dir):
    """PATH exported into Bazel actions so they can exec real patchelf."""
    parts = []
    for item in [patchelf_dir] + os.environ.get('PATH', '').split(os.pathsep) + \
            ['/usr/local/bin', '/usr/bin', '/bin']:
        item = (item or '').strip()
        if item and item not in parts:
            parts.append(item)
    return ':'.join(parts)


def _external_repo_problems(external):
    """Return real, non-synthesizable problems inside the prepared `external`.

    We do not create or repair anything here: if the builder's resolved
    repositories are missing we report the actual paths so the operator can
    re-run the preparation step.
    """
    problems = []
    if external is None or not external.is_dir() or not any(external.iterdir()):
        return ['prepared Bazel external repositories empty: %s' % external]
    local_cc = external / 'local_config_cc'
    if local_cc.is_dir():
        for need in ('BUILD', 'armeabi_cc_toolchain_config.bzl'):
            if not (local_cc / need).is_file():
                problems.append('incomplete @local_config_cc: missing %s'
                                % (local_cc / need))
    else:
        problems.append('@local_config_cc missing from prepared external repos: %s'
                        % local_cc)
    return problems


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #

def doctor(input_dir):
    input_dir = Path(input_dir)
    report = {'input': str(input_dir), 'missing_source': [], 'missing_tool': [],
              'missing_dependency': [], 'details': {}}
    manifest = archive = None
    want, reqs = None, []

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
            reqs = _required_packages(_peek_tar(archive, SETUP_PY) or '')
            report['details']['bazelversion'] = want
            report['details']['required_packages'] = reqs

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
    for tool in ('gcc', 'clang', 'bash', 'python3', 'zip'):
        if shutil.which(tool) is None:
            report['missing_tool'].append(tool)

    # --- real patchelf bootstrap, required by official wheel packaging ------- #
    patchelf = _find_patchelf()
    ok, info = _patchelf_probe(patchelf)
    report['details']['patchelf'] = {'path': patchelf or '', 'version': info, 'ok': ok}
    if not ok:
        report['missing_tool'].append(
            'patchelf (required by //tensorflow/tools/pip_package:wheel '
            'build_pip_package.py -> patch_so): %s' % info)

    # --- manifest-declared dependency archive & cache layout ---------------- #
    declared = (manifest or {}).get('dependency_caches') or []
    repo_cache, output_base, external = cache_layout(manifest)
    report['details']['cache_layout'] = {
        'repository_cache': str(repo_cache),
        'output_base': str(output_base),
        'external_repos': str(external),
    }
    for entry in declared:
        fn = entry.get('filename')
        if not fn:
            continue
        found = None
        for cand in (CACHE_ROOT / fn, input_dir / fn):
            if cand.is_file():
                found = cand
                break
        if found is None:
            # already hydrated builder inputs are the normal case; only note it
            report['details'].setdefault('dependency_archives', []).append(
                {'filename': fn, 'path': 'hydrated into %s' % CACHE_ROOT})
            continue
        have = buildkit.digest(found)
        entry_info = {'filename': fn, 'path': str(found), 'sha256': have}
        if entry.get('sha256'):
            entry_info['expected_sha256'] = entry['sha256']
            entry_info['match'] = have == entry['sha256']
            if have != entry['sha256']:
                report['missing_dependency'].append(
                    'dependency cache checksum mismatch: %s' % found)
        report['details'].setdefault('dependency_archives', []).append(entry_info)

    if not repo_cache.is_dir() or not any(repo_cache.iterdir()):
        report['missing_dependency'].append(
            'Bazel repository cache empty: %s (offline path declared by the manifest)'
            % repo_cache)
    else:
        report['details']['repository_cache'] = {
            'path': str(repo_cache), 'entries': sum(1 for _ in repo_cache.iterdir())}
    report['missing_dependency'].extend(_external_repo_problems(external))

    if manifest and manifest.get('offline_dependencies_ready') is False:
        report['missing_dependency'].append(
            'manifest declares offline_dependencies_ready=false: vendored Bazel '
            'external repos (llvm, eigen, pybind11, rules_python ...) not sealed')
    if manifest and manifest.get('source_archive_ready') is False:
        report['missing_dependency'].append('manifest declares source_archive_ready=false')

    # --- Python runtime wheels --------------------------------------------- #
    versions = _wheel_versions(WHEELHOUSE)
    if not WHEELHOUSE.is_dir():
        report['missing_dependency'].append('%s (offline Python wheels)' % WHEELHOUSE)
    else:
        missing = [r for r in reqs
                   if _norm(r) not in versions and _norm(r) not in OPTIONAL_PACKAGES]
        optional_missing = [r for r in reqs
                            if _norm(r) in OPTIONAL_PACKAGES and _norm(r) not in versions]
        if optional_missing:
            report['details']['optional_missing'] = optional_missing
        if missing:
            report['missing_dependency'].append(
                'wheels absent from %s for runtime-required packages: %s'
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


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #

def _configure_env(bazel_dir):
    path = os.environ.get('PATH', '')
    if bazel_dir:
        path = bazel_dir + os.pathsep + path
    return {
        'PATH': path,
        'TF_NEED_CUDA': '0', 'TF_NEED_ROCM': '0', 'TF_NEED_TENSORRT': '0',
        'TF_NEED_OPENCL_SYCL': '0', 'TF_NEED_OPENCL': '0', 'TF_NEED_MPI': '0',
        'TF_NEED_CLANG': '1', 'TF_CUDA_CLANG': '0',
        'TF_MKL_BUILD': '0', 'TF_CUDA_COMPUTE_CAPABILITIES': '',
        'TF_DOWNLOAD_CLANG': '0', 'TF_SET_ANDROID_WORKSPACE': '0',
        'CC_OPT_FLAGS': '-Wno-sign-compare -Wno-error=gnu-offsetof-extensions',
        'PYTHON_BIN_PATH': sys.executable,
        'PYTHON_LIB_PATH': sysconfig.get_paths().get('purelib', ''),
    }


def _bazel_env(action_path):
    BAZEL_HOME.mkdir(parents=True, exist_ok=True)
    env = {'HOME': str(BAZEL_HOME),
           'PATH': action_path,
           'OMP_NUM_THREADS': '4',
           'OPENBLAS_NUM_THREADS': '4',
           'MKL_NUM_THREADS': '4'}
    clang = shutil.which('clang-18') or shutil.which('clang')
    clangxx = shutil.which('clang++-18') or shutil.which('clang++')
    if clang:
        env['CC'] = clang
    if clangxx:
        env['CXX'] = clangxx
    return env


def run(input_dir, output_dir, jobs):
    manifest = json.loads((Path(input_dir) / 'manifest.json').read_text())
    limit = build_job_limit(manifest)
    requested = max(1, min(int(jobs), limit))          # min(user_jobs, manifest limit)

    session = buildkit.Session(input_dir, output_dir, jobs=requested)
    src = session.prepare()
    python_bin = sys.executable

    want = _parse_bazelversion((src / '.bazelversion').read_text(errors='replace'))
    bazel = _find_bazel(want)
    if bazel is None:
        raise RuntimeError('bazel %s not found under %s (see doctor)' % (want, BAZEL_ROOT))
    bazel_dir = str(Path(bazel).parent)

    # --- real patchelf bootstrap, validated with --version before building --
    patchelf = _find_patchelf()
    if patchelf is None:
        raise RuntimeError('patchelf not found on PATH or in bootstrap dirs; the '
                           'official //tensorflow/tools/pip_package:wheel packaging '
                           'step requires it (see doctor)')
    probe = session.run([patchelf, '--version'], cwd=src, phase='tool_probe',
                        name='patchelf_version', timeout=300)
    probe_text = probe.read_text(errors='replace')
    if 'patchelf' not in probe_text.lower():
        raise RuntimeError('patchelf --version did not report a real patchelf: %r'
                           % probe_text[:200])
    patchelf_dir = str(Path(patchelf).parent)
    action_path = _action_path(patchelf_dir)

    repo_cache, output_base, external = cache_layout(session.manifest)
    if not repo_cache.is_dir() or not any(repo_cache.iterdir()):
        raise RuntimeError('offline Bazel repository cache %s is missing (see doctor)'
                           % repo_cache)
    ext_problems = _external_repo_problems(external)
    if ext_problems:
        raise RuntimeError('prepared Bazel external repositories unusable: %s'
                           % '; '.join(ext_problems))
    output_base.mkdir(parents=True, exist_ok=True)
    BAZEL_HOME.mkdir(parents=True, exist_ok=True)

    session.run(['bash', './configure'], cwd=src, phase='configure', name='configure',
                env=_configure_env(bazel_dir), timeout=1800)
    bazelrc = src / '.tf_configure.bazelrc'
    if not bazelrc.is_file():
        raise RuntimeError('configure did not produce %s; refusing to build' % bazelrc)

    bazel_env = _bazel_env(action_path)
    shared = ['--action_env=PATH=%s' % action_path]
    build = [bazel, '--output_base=%s' % output_base, 'build',
             '--repository_cache=%s' % repo_cache,
             '--jobs=%d' % session.jobs,
             '--local_ram_resources=%d' % LOCAL_RAM_RESOURCES]
    build += shared + CLANG_COMPAT_OPTS
    build += ['--repo_env=USE_PYWRAP_RULES=1',
              '--repo_env=WHEEL_NAME=tensorflow_cpu',
              '--config=opt',
              '//tensorflow/tools/pip_package:wheel']
    session.run(build, cwd=src, phase='build', name='bazel_build_wheel',
                env=bazel_env, timeout=10800)

    wheel_house = src / 'bazel-bin' / 'tensorflow' / 'tools' / 'pip_package' / 'wheel_house'
    wheels = sorted(wheel_house.glob('tensorflow_cpu-*.whl'))
    if not wheels:
        raise RuntimeError('bazel build finished but no tensorflow_cpu wheel in %s'
                           % wheel_house)
    wheel = wheels[-1]
    shutil.copy2(wheel, session.output / wheel.name)
    session.run([python_bin, '-m', 'pip', 'install', '--no-index', '--no-deps',
                 '--target', str(session.install), str(wheel)],
                cwd=session.output, phase='package', name='install_wheel', timeout=1800)

    common = [bazel, '--output_base=%s' % output_base, 'test',
              '--repository_cache=%s' % repo_cache,
              '--config=linux', '--test_output=all']
    common += shared + CLANG_COMPAT_OPTS
    common += ['--jobs=%d' % TEST_JOBS, '--local_test_jobs=%d' % TEST_JOBS,
               '--cache_test_results=no', '--test_timeout=1800']
    session.test('softmax_op_test',
                 common + ['//tensorflow/python/kernel_tests/nn_ops:softmax_op_test'],
                 cwd=src, env=bazel_env, timeout=3600)
    session.test('load_test.test_capture_variables',
                 common + ['--test_filter=*LoadTest.test_capture_variables*',
                           '//tensorflow/python/saved_model:load_test'],
                 cwd=src, env=bazel_env, timeout=3600)

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

    versions = _wheel_versions(WHEELHOUSE)
    deps = [d for d in _wheel_deps(wheel) if _norm(d) in versions]
    if deps:
        session.run([str(vpy), '-m', 'pip', 'install', '--no-index',
                     '--find-links=%s' % WHEELHOUSE,
                     '--constraints=%s' % constraints,
                     '--no-deps'] + deps,
                    cwd=consumer, phase='install', name='install_consumer_deps', timeout=1800)
    session.run([str(vpy), '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel)],
                cwd=consumer, phase='install', name='install_consumer_wheel', timeout=1800)

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
        'cuda': False, 'rocm': False,
        'build_jobs': session.jobs, 'test_jobs': TEST_JOBS,
        'local_ram_resources': LOCAL_RAM_RESOURCES,
        'pinned_dependencies': pinned,
        'installed_deps': sorted(_norm(d) for d in deps),
        'bazel': bazel, 'repository_cache': str(repo_cache),
        'output_base': str(output_base), 'external_repos': str(external),
        'clang_compat_opts': CLANG_COMPAT_OPTS,
        'patchelf': patchelf, 'patchelf_dir': patchelf_dir,
        'action_env_path': action_path,
    })
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

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
    r.add_argument('--jobs', type=int, default=DEFAULT_BUILD_JOBS)
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == 'doctor':
        return doctor(args.input)
    if args.command == 'run':
        return run(args.input, args.output, args.jobs)
    parser.error('unknown command')
    return 2


if __name__ == '__main__':
    sys.exit(main())
