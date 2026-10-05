#!/usr/bin/env python3
# BUILDv1-F10 -- ONNX Runtime CPU wheel + native runtime builder (frozen CORE profile).
# All build/configure/install/test/consumer subprocesses go through the trusted
# buildkit.Session so logs and exit codes are preserved. No network is used:
# every prepared dependency tree in the manifest dependency cache is handed to
# CMake through FETCHCONTENT_SOURCE_DIR_<NAME>.
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit

TASK_ID = 'BUILDv1-F10'
REQUIRED_TOOLS = ['cmake', 'ninja', 'gcc', 'g++', 'git', 'python3', 'bash']
REQUIRED_MODULES = ['setuptools', 'packaging']
NEEDED_IN_ARCHIVE = ('build.sh', 'setup.py', 'cmake/CMakeLists.txt', 'cmake/deps.txt')
WHEELHOUSE = Path('/opt/wheelhouse')
CONSUMER_REQUIREMENTS = ['onnx', 'numpy']
DEFAULT_DEPS_ROOT = Path('/workspace/cache/ort_deps')
CMAKE_GLOBS = ('opt/cmake-*/bin/cmake', 'opt/cmake*/bin/cmake', 'usr/local/bin/cmake', 'usr/bin/cmake')
FALLBACK_CMAKE_MINIMUM = (3, 26)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(input_dir):
    path = Path(input_dir) / 'manifest.json'
    if not path.is_file():
        return None, ['manifest missing: ' + str(path)]
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return None, ['manifest unreadable: ' + str(path) + ': ' + str(exc)]
    source = data.get('source') or {}
    problems = []
    if not source.get('filename'):
        problems.append('manifest missing source.filename')
    if not source.get('sha256'):
        problems.append('manifest missing source.sha256')
    return data, problems


def deps_cache_root(manifest):
    for cache in (manifest or {}).get('dependency_caches') or []:
        destination = cache.get('destination')
        if destination:
            return Path(destination)
    return DEFAULT_DEPS_ROOT


def scan_archive(archive):
    """Stream the frozen tarball collecting required files and the source
    cmake_minimum_required without unpacking it."""
    found = {}
    minimum = None
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            if not member.isfile():
                continue
            parts = member.name.split('/', 1)
            relative = parts[1] if len(parts) == 2 else member.name
            if relative in NEEDED_IN_ARCHIVE or relative == 'CMakeLists.txt':
                found[relative] = True
                if relative.endswith('CMakeLists.txt'):
                    stream = tar.extractfile(member)
                    text = stream.read(1 << 20).decode('utf-8', 'replace') if stream else ''
                    match = re.search(r'cmake_minimum_required\s*\(\s*VERSION\s+([0-9]+)\.([0-9]+)', text)
                    if match:
                        candidate = (int(match.group(1)), int(match.group(2)))
                        minimum = candidate if minimum is None else max(minimum, candidate)
    return found, minimum


def cmake_version(cmake_bin):
    try:
        result = subprocess.run([str(cmake_bin), '--version'], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', result.stdout or '')
    return tuple(int(part) for part in match.groups()) if match else None


def select_cmake(minimum):
    candidates = []
    for pattern in CMAKE_GLOBS:
        candidates.extend(sorted(Path('/').glob(pattern)))
    available = []
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            version = cmake_version(candidate)
            if version:
                available.append((version, candidate))
    for version, candidate in available:
        if version >= tuple(minimum):
            return candidate, version
    if available:
        available.sort(reverse=True)
        return None, available[0][0]
    return None, None


def fetchcontent_names(src):
    names = set()
    external = src / 'cmake' / 'external'
    if external.is_dir():
        for path in sorted(external.glob('*.cmake')):
            text = path.read_text(errors='replace')
            for match in re.finditer(r'fetchcontent_declare\s*\(\s*([A-Za-z0-9_]+)', text):
                names.add(match.group(1))
    return names


def detect_define_style(src):
    """Decide whether the frozen build.py adds the '-D' prefix for
    --cmake_extra_defines itself ('bare') or passes tokens through ('dashd')."""
    path = src / 'tools' / 'ci_build' / 'build.py'
    try:
        text = path.read_text(errors='replace')
    except OSError:
        return 'dashd'
    for match in re.finditer(r'cmake_extra_defines', text):
        window = text[match.start(): match.start() + 900]
        if re.search(r'["\']-D["\']', window) or 'f"-D{' in window or "f'-D{" in window:
            return 'bare'
    return 'dashd'


def wheelhouse_problems(requirements):
    if not WHEELHOUSE.is_dir():
        return ['offline wheelhouse missing: ' + str(WHEELHOUSE)]
    listing = ' '.join(entry.name.lower() for entry in WHEELHOUSE.iterdir())
    return ['offline wheel missing from ' + str(WHEELHOUSE) + ': ' + name
            for name in requirements if name not in listing]


def collect_missing(input_dir):
    """Exact list of missing source/tool/dependency items; empty means ready."""
    input_dir = Path(input_dir)
    manifest, problems = load_manifest(input_dir)
    missing = list(problems)
    archive_minimum = None
    if manifest:
        archive = input_dir / manifest['source']['filename']
        if not archive.is_file():
            missing.append('frozen source archive missing: ' + str(archive))
        else:
            expected = str(manifest['source']['sha256']).lower()
            actual = sha256(archive)
            if actual != expected:
                missing.append('source archive sha256 mismatch: expected ' + expected + ' got ' + actual)
            else:
                try:
                    found, archive_minimum = scan_archive(archive)
                except (tarfile.TarError, OSError, EOFError) as exc:
                    missing.append('source archive unreadable as tar: ' + str(archive) + ': ' + str(exc))
                    found = {}
                for relative in NEEDED_IN_ARCHIVE:
                    if relative not in found:
                        missing.append('required source file missing from archive: ' + relative)

    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append('build tool missing on PATH: ' + tool)
    for module in REQUIRED_MODULES:
        try:
            from importlib.util import find_spec
            if find_spec(module) is None:
                missing.append('build python module missing: ' + module)
        except (ImportError, ValueError):
            missing.append('build python module missing: ' + module)

    minimum = archive_minimum or FALLBACK_CMAKE_MINIMUM
    cmake_bin, version = select_cmake(minimum)
    if cmake_bin is None:
        if version is None:
            missing.append('no usable CMake found (need >= %d.%d)' % minimum)
        else:
            missing.append('CMake >= %d.%d required by the frozen source, highest available is %d.%d'
                           % (minimum[0], minimum[1], version[0], version[1]))

    if manifest:
        root = deps_cache_root(manifest)
        if not root.is_dir():
            missing.append('prepared dependency cache root missing: ' + str(root))
        else:
            for dep in manifest.get('cpu_dependency_sources') or []:
                name = dep.get('name')
                if not name:
                    continue
                path = root / name
                if not path.is_dir():
                    missing.append('prepared CPU dependency source tree missing: ' + str(path))
                elif not any(path.iterdir()):
                    missing.append('prepared CPU dependency source tree is empty: ' + str(path))

    missing.extend(wheelhouse_problems(CONSUMER_REQUIREMENTS))
    return missing


def cmd_doctor(input_dir):
    print(TASK_ID + ' doctor: inspecting ' + str(input_dir))
    missing = collect_missing(input_dir)
    if missing:
        print(json.dumps({'task_id': TASK_ID, 'command': 'doctor', 'input': str(input_dir),
                          'status': 'not-ready', 'missing_count': len(missing), 'missing': missing}, indent=2))
        print('doctor: NOT READY (' + str(len(missing)) + ' item(s) missing)', file=sys.stderr)
        return 78
    manifest, _ = load_manifest(input_dir)
    source = manifest['source']
    print(json.dumps({'task_id': TASK_ID, 'command': 'doctor', 'input': str(input_dir), 'status': 'ready',
                      'source': {'filename': source['filename'], 'sha256': source['sha256'],
                                 'release_ref': source.get('release_ref')},
                      'dependency_cache': str(deps_cache_root(manifest)),
                      'prepared_dependencies': len(manifest.get('cpu_dependency_sources') or []),
                      'build_jobs': 4, 'test_jobs': 2}, indent=2))
    return 0


def archive_minimum(src):
    minimum = None
    for relative in ('CMakeLists.txt', 'cmake/CMakeLists.txt'):
        path = src / relative
        if not path.is_file():
            continue
        match = re.search(r'cmake_minimum_required\s*\(\s*VERSION\s+([0-9]+)\.([0-9]+)',
                          path.read_text(errors='replace'))
        if match:
            candidate = (int(match.group(1)), int(match.group(2)))
            minimum = candidate if minimum is None else max(minimum, candidate)
    return minimum


def cmd_run(input_dir, output_dir, jobs):
    missing = collect_missing(input_dir)
    if missing:
        print(json.dumps({'task_id': TASK_ID, 'command': 'run', 'status': 'not-ready',
                          'missing_count': len(missing), 'missing': missing}, indent=2))
        print('run: refusing to build; environment is not ready', file=sys.stderr)
        return 78

    jobs = max(1, min(int(jobs), 4))
    test_jobs = max(1, min(2, jobs))
    session = buildkit.Session(input_dir, output_dir, jobs=jobs)
    session.prepare()
    src = session.src
    manifest = session.manifest
    build_root = session.build
    config_dir = build_root / 'Release'

    # Every prepared dependency tree is injected into its FetchContent
    # declaration so configure never reaches the network.
    deps_root = deps_cache_root(manifest)
    prepared = [d['name'] for d in manifest.get('cpu_dependency_sources') or []
                if d.get('name') and (deps_root / d['name']).is_dir()]
    declared = fetchcontent_names(src)
    upper_declared = {name.upper() for name in declared}
    source_dirs = ['FETCHCONTENT_SOURCE_DIR_' + name.upper() + '=' + str(deps_root / name)
                   for name in prepared]
    session.write('dependency_map.json', {
        'dependency_cache_root': str(deps_root), 'prepared_count': len(prepared),
        'prepared': prepared, 'declared_fetchcontent_names': sorted(declared),
        'prepared_without_matching_declaration': sorted(
            name for name in prepared if name.upper() not in upper_declared)})

    minimum = archive_minimum(src) or FALLBACK_CMAKE_MINIMUM
    cmake_bin, _ = select_cmake(minimum)
    env = {'BUILD_JOBS': str(jobs), 'OMP_NUM_THREADS': str(test_jobs), 'ORT_OPENMP_THREADS': str(test_jobs),
           'PYTHONDONTWRITEBYTECODE': '1'}
    if cmake_bin is not None:
        env['PATH'] = str(cmake_bin.parent) + os.pathsep + os.environ.get('PATH', '')

    extras = ['onnxruntime_BUILD_UNIT_TESTS=ON'] + source_dirs
    base = ['bash', str(src / 'build.sh'), '--config', 'Release', '--build_dir', str(build_root),
            '--build_shared_lib', '--build_wheel', '--parallel', str(jobs),
            '--skip_submodule_sync', '--update', '--build', '--cmake_generator', 'Ninja']
    style = detect_define_style(src)

    def build_command(define_style):
        prefix = '-D' if define_style == 'dashd' else ''
        return base + ['--cmake_extra_defines'] + [prefix + item for item in extras]

    def clean_build_tree():
        for entry in build_root.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()

    log = session.run(build_command(style), cwd=src, phase='configure+build',
                      name='ort_build_' + style, env=env, timeout=10800, check=False)
    record = session.commands[-1]
    if record['exit_code'] != 0:
        text = log.read_text(errors='replace')
        markers = ('Unknown argument', 'FETCHCONTENT_SOURCE_DIR', 'Could not resolve', 'Failed to download')
        if any(marker in text for marker in markers) and record['wall_seconds'] < 1800:
            alternate = 'bare' if style == 'dashd' else 'dashd'
            clean_build_tree()
            session.run(build_command(alternate), cwd=src, phase='configure+build',
                        name='ort_build_' + alternate, env=env, timeout=10800, check=True)
        else:
            raise RuntimeError('source build failed:\n' + text[-8000:])

    # Official upstream CPU runtime and shared-library test binaries.
    for binary in ('onnxruntime_test_all', 'onnxruntime_shared_lib_test'):
        binary_path = config_dir / binary
        if not binary_path.is_file():
            raise RuntimeError('expected upstream test binary was not built: ' + str(binary_path))
        session.test(binary, [str(binary_path), '--gtest_output=xml:' + binary + '.xml', '--gtest_color=no'],
                     cwd=config_dir, env=env, timeout=7200)

    # Package strictly from this build's own dist directory.
    wheels = sorted((config_dir / 'dist').glob('*.whl'))
    if not wheels:
        raise RuntimeError('no wheel produced under ' + str(config_dir / 'dist'))
    wheel = wheels[0]
    if wheel.stat().st_size < (1 << 20):
        raise RuntimeError('built wheel looks truncated, refusing to ship: ' + str(wheel))
    staged = session.output / wheel.name
    shutil.copy2(wheel, staged)

    # Fresh consumer environment, offline install of the newly built wheel.
    venv = session.consumer / 'venv'
    if venv.exists():
        shutil.rmtree(venv)
    session.run([sys.executable, '-m', 'venv', str(venv)], cwd=session.consumer,
                phase='package', name='consumer_venv')
    pip = str(venv / 'bin' / 'pip')
    session.run([pip, 'install', '--no-index', '--find-links', str(WHEELHOUSE), '--no-deps', str(staged)],
                cwd=session.consumer, phase='package', name='install_new_wheel')
    session.run([pip, 'install', '--no-index', '--find-links', str(WHEELHOUSE)] + CONSUMER_REQUIREMENTS,
                cwd=session.consumer, phase='package', name='install_consumer_deps')

    consumer = Path(__file__).resolve().parent / 'consumer_ort.py'
    session.run([str(venv / 'bin' / 'python'), str(consumer),
                 '--report', str(session.output / 'consumer_report.json')],
                cwd=session.consumer, phase='consumer', name='consume_ort_graph', timeout=900)

    session.finish(features={
        'wheel': staged.name, 'wheel_sha256': sha256(staged), 'shared_lib_built': True,
        'execution_provider': 'CPUExecutionProvider',
        'official_tests': ['onnxruntime_test_all', 'onnxruntime_shared_lib_test'],
        'prepared_dependencies': len(prepared), 'fetchcontent_source_dirs': len(source_dirs),
        'cmake_extra_define_style': style, 'cmake': str(cmake_bin) if cmake_bin else 'PATH cmake',
        'build_jobs': jobs, 'test_jobs': test_jobs, 'consumer_venv': str(venv)})
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog='main.py',
        description=TASK_ID + ': build an ONNX Runtime CPU wheel and native shared library from the '
                    'frozen source release, run the official runtime/shared-library tests, then consume '
                    'the new wheel from a fresh environment outside the source tree.')
    sub = parser.add_subparsers(dest='command')
    doctor = sub.add_parser('doctor', help='report exact missing source/tool/dependency items')
    doctor.add_argument('--input', required=True)
    run = sub.add_parser('run', help='build, test, package and independently consume')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command == 'doctor':
        return cmd_doctor(args.input)
    return cmd_run(args.input, args.output, args.jobs)


if __name__ == '__main__':
    sys.exit(main())
