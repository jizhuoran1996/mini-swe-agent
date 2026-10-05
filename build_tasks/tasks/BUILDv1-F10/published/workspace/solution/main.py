#!/usr/bin/env python3
# BUILDv1-F10 -- ONNX Runtime CPU wheel + native runtime builder (frozen CORE profile).
#
# Every build/configure/install/test/consumer subprocess goes through the trusted
# buildkit.Session so logs and exit codes are preserved. The build is fully offline:
# each prepared dependency tree under the manifest dependency cache is injected into
# CMake as -DFETCHCONTENT_SOURCE_DIR_<NAME>=... (the -D prefix is added by ORT's own
# build.sh, which is why the raw values are passed without it).
import argparse
import glob as globmod
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
# 'cmake' is intentionally absent: it may be bootstrapped from the offline wheelhouse.
REQUIRED_TOOLS = ['ninja', 'gcc', 'g++', 'git', 'python3', 'bash']
REQUIRED_MODULES = ['setuptools', 'packaging']
NEEDED_IN_ARCHIVE = ('build.sh', 'setup.py', 'cmake/CMakeLists.txt', 'cmake/deps.txt')
WHEELHOUSE = Path('/opt/wheelhouse')
CONSUMER_REQUIREMENTS = ['onnx', 'numpy']
DEFAULT_DEPS_ROOT = Path('/workspace/cache/ort_deps')
CMAKE_GLOBS = ('/opt/cmake-*/bin/cmake', '/opt/cmake*/bin/cmake',
               '/usr/local/bin/cmake', '/usr/bin/cmake')
FALLBACK_CMAKE_MINIMUM = (3, 26)
# Matches both FetchContent_Declare(...) and onnxruntime_fetchcontent_declare(...).
DECLARE_RE = re.compile(r'(?:onnxruntime_)?fetchcontent_declare\s*\(\s*([A-Za-z0-9_.\-]+)', re.I)
CMAKE_WHEEL_RE = re.compile(r'^cmake-(\d+)\.(\d+)\.(\d+)')


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
        if cache.get('destination'):
            return Path(cache['destination'])
    return DEFAULT_DEPS_ROOT


def scan_archive(archive):
    """Stream the frozen tarball for the required files and the real
    cmake_minimum_required, without unpacking it to disk."""
    found, minimum = {}, None
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            if not member.isfile():
                continue
            parts = member.name.split('/', 1)
            relative = parts[1] if len(parts) == 2 else member.name
            if relative not in NEEDED_IN_ARCHIVE and not relative.endswith('CMakeLists.txt'):
                continue
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


def system_cmakes():
    """Real system CMake binaries with parsed versions, newest first."""
    found = {}
    for pattern in CMAKE_GLOBS:
        for raw in globmod.glob(pattern):
            path = Path(raw)
            if path in found:
                continue
            if not path.is_file() or not os.access(path, os.X_OK):
                continue
            version = cmake_version(path)
            if version:
                found[path] = version
    return sorted(((version, path) for path, version in found.items()), reverse=True)


def wheelhouse_cmake():
    """Newest CMake wheel (version, path) in the offline wheelhouse, or None."""
    best = None
    if not WHEELHOUSE.is_dir():
        return None
    for wheel in sorted(WHEELHOUSE.glob('cmake-*.whl')):
        match = CMAKE_WHEEL_RE.match(wheel.name)
        if not match:
            continue
        version = tuple(int(part) for part in match.groups())
        if best is None or version > best[0]:
            best = (version, wheel)
    return best


def cmake_readiness(minimum):
    """Return (ok, detail). ok is True when a satisfying CMake exists on the
    system or can be bootstrapped offline from the wheelhouse."""
    system = system_cmakes()
    for version, path in system:
        if version >= minimum:
            return True, 'system CMake %d.%d.%d at %s' % (version + (str(path),))
    wheel = wheelhouse_cmake()
    if wheel and wheel[0] >= minimum:
        return True, 'offline CMake %d.%d.%d wheel %s' % (wheel[0] + (wheel[1].name,))
    required = 'CMake >= %d.%d required by the frozen source' % minimum
    if system:
        return False, required + ', newest on the system is %d.%d.%d' % system[0][0]
    if wheel:
        return False, required + ', newest wheelhouse cmake wheel is %d.%d.%d' % wheel[0]
    return False, required + ', no CMake found and no wheelhouse cmake wheel present'


def declared_fetchcontent_names(src):
    """Collect the FetchContent names the frozen CMake tree actually declares."""
    names = set()
    for root in (src / 'cmake' / 'external', src / 'cmake'):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*.cmake')):
            if 'vcpkg' in path.parts:
                continue
            for match in DECLARE_RE.finditer(path.read_text(errors='replace')):
                name = match.group(1)
                if name and not name.startswith('$'):
                    names.add(name)
    return names


def normalize(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())


def resolve_source_root(path):
    """Some prepared trees are wrapped in a single inner directory; point
    FetchContent at the directory that actually holds the project."""
    if (path / 'CMakeLists.txt').is_file():
        return path
    entries = list(path.iterdir())
    dirs = [e for e in entries if e.is_dir()]
    files = [e for e in entries if e.is_file()]
    if not files and len(dirs) == 1 and any(dirs[0].iterdir()):
        return dirs[0]
    return path


def build_source_dir_defines(prepared_dirs, declared):
    """Map every declared FetchContent name onto the prepared tree whose
    directory name corresponds to it (they are usually equal, but a few differ)."""
    normalized = {p.name: normalize(p.name) for p in prepared_dirs}
    defines = {}
    for declared_name in sorted(declared):
        target = normalize(declared_name)
        chosen = next((p for p in prepared_dirs if normalized[p.name] == target), None)
        if chosen is None and target:
            ranked = [(abs(len(normalized[p.name]) - len(target)), -len(normalized[p.name]), p)
                      for p in prepared_dirs
                      if target in normalized[p.name] or normalized[p.name] in target]
            if ranked:
                ranked.sort(key=lambda item: (item[0], item[1]))
                chosen = ranked[0][2]
        if chosen is not None:
            defines['FETCHCONTENT_SOURCE_DIR_' + declared_name.upper()] = chosen
    # Always keep the directory-derived variable too; unused -D variables are only a warning.
    for path in prepared_dirs:
        defines.setdefault('FETCHCONTENT_SOURCE_DIR_' + path.name.upper(), path)
    return defines


def wheelhouse_problems(requirements, wheelhouse=WHEELHOUSE):
    if not wheelhouse.is_dir():
        return ['offline wheelhouse missing: ' + str(wheelhouse)]
    listing = ' '.join(entry.name.lower() for entry in wheelhouse.iterdir())
    return ['offline wheel missing from ' + str(wheelhouse) + ': ' + name
            for name in requirements if name not in listing]


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


def collect_missing(input_dir):
    """Exact list of missing source/tool/dependency items; empty means ready."""
    input_dir = Path(input_dir)
    manifest, problems = load_manifest(input_dir)
    missing = list(problems)
    archive_min = None
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
                    found, archive_min = scan_archive(archive)
                except (tarfile.TarError, OSError, EOFError) as exc:
                    missing.append('source archive unreadable as tar: ' + str(archive) + ': ' + str(exc))
                    found = {}
                for relative in NEEDED_IN_ARCHIVE:
                    if relative not in found:
                        missing.append('required source file missing from archive: ' + relative)

    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append('build tool missing on PATH: ' + tool)
    from importlib.util import find_spec
    for module in REQUIRED_MODULES:
        try:
            if find_spec(module) is None:
                missing.append('build python module missing: ' + module)
        except (ImportError, ValueError):
            missing.append('build python module missing: ' + module)

    minimum = archive_min or FALLBACK_CMAKE_MINIMUM
    ok, detail = cmake_readiness(minimum)
    if not ok:
        missing.append(detail)

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
    ok, detail = cmake_readiness(FALLBACK_CMAKE_MINIMUM)
    print(json.dumps({'task_id': TASK_ID, 'command': 'doctor', 'input': str(input_dir), 'status': 'ready',
                      'source': {'filename': source['filename'], 'sha256': source['sha256'],
                                 'release_ref': source.get('release_ref')},
                      'layout': 'FetchContent (cmake/deps.txt + cmake/CMakeLists.txt)',
                      'cmake_status': detail,
                      'dependency_cache': str(deps_cache_root(manifest)),
                      'prepared_dependencies': len(manifest.get('cpu_dependency_sources') or []),
                      'build_jobs': 4, 'test_jobs': 2}, indent=2))
    return 0


def bootstrap_cmake(session, minimum):
    """Return the directory containing a satisfying cmake binary. Uses a real
    system CMake when one is new enough, otherwise installs the official CMake
    wheel from the offline wheelhouse into a workspace tool venv."""
    for version, path in system_cmakes():
        if version >= minimum:
            return path.parent, version
    wheel = wheelhouse_cmake()
    if wheel is None or wheel[0] < minimum:
        raise RuntimeError('no CMake >= %d.%d available on the system or in the wheelhouse'
                           % minimum)
    toolvenv = session.output / 'toolvenv'
    if toolvenv.exists():
        shutil.rmtree(toolvenv)
    session.run([sys.executable, '-m', 'venv', str(toolvenv)], cwd=session.output,
                phase='bootstrap', name='cmake_tool_venv')
    pip = toolvenv / 'bin' / 'pip'
    session.run([str(pip), 'install', '--no-index', '--find-links', str(WHEELHOUSE), 'cmake'],
                cwd=session.output, phase='bootstrap', name='install_cmake_wheel')
    cmake_bin = toolvenv / 'bin' / 'cmake'
    version = cmake_version(cmake_bin)
    if version is None:
        raise RuntimeError('bootstrapped CMake at ' + str(cmake_bin) + ' is not runnable')
    return cmake_bin.parent, version


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
    deps_root = deps_cache_root(manifest)

    minimum = archive_minimum(src) or FALLBACK_CMAKE_MINIMUM
    cmake_dir, cmake_ver = bootstrap_cmake(session, minimum)

    prepared_names = [d['name'] for d in manifest.get('cpu_dependency_sources') or []
                      if d.get('name') and (deps_root / d['name']).is_dir()]
    prepared_dirs = [resolve_source_root(deps_root / name) for name in prepared_names]
    declared = declared_fetchcontent_names(src)
    defines = build_source_dir_defines(prepared_dirs, declared)
    session.write('dependency_map.json', {
        'dependency_cache_root': str(deps_root), 'prepared_count': len(prepared_dirs),
        'prepared_names': prepared_names,
        'prepared_roots': {d['name']: str(resolve_source_root(deps_root / d['name'])) for d in
                           (manifest.get('cpu_dependency_sources') or []) if d.get('name') and
                           (deps_root / d['name']).is_dir()},
        'declared_fetchcontent_names': sorted(declared),
        'source_dir_defines': {name: str(path) for name, path in sorted(defines.items())}})

    env = {'BUILD_JOBS': str(jobs), 'OMP_NUM_THREADS': str(test_jobs), 'ORT_OPENMP_THREADS': str(test_jobs),
           'PYTHONDONTWRITEBYTECODE': '1',
           'PATH': str(cmake_dir) + os.pathsep + os.environ.get('PATH', '')}

    # ORT's build.sh prepends '-D' to each --cmake_extra_defines value itself, so the
    # raw 'NAME=VALUE' tokens are what must be handed to it (they would be rejected as
    # options by build.py's argparse if they already carried a leading '-D').
    extra_defines = ['onnxruntime_BUILD_UNIT_TESTS=ON']
    extra_defines += [name + '=' + str(path) for name, path in sorted(defines.items())]
    build_argv = ['bash', str(src / 'build.sh'), '--config', 'Release', '--build_dir', str(build_root),
                  '--build_shared_lib', '--build_wheel', '--parallel', str(jobs),
                  '--skip_submodule_sync', '--update', '--build', '--cmake_generator', 'Ninja',
                  '--cmake_extra_defines'] + extra_defines
    log = session.run(build_argv, cwd=src, phase='configure+build', name='ort_build',
                      env=env, timeout=10800, check=False)
    record = session.commands[-1]
    if record['exit_code'] != 0:
        tail = log.read_text(errors='replace')[-12000:]
        raise RuntimeError('source configure/build failed (exit %s)\n%s' % (record['exit_code'], tail))

    # Unchanged official upstream CPU runtime and shared-library test binaries.
    for binary in ('onnxruntime_test_all', 'onnxruntime_shared_lib_test'):
        binary_path = config_dir / binary
        if not binary_path.is_file():
            raise RuntimeError('expected upstream test binary was not built: ' + str(binary_path))
        session.test(binary, [str(binary_path), '--gtest_output=xml:' + binary + '.xml', '--gtest_color=no'],
                     cwd=config_dir, env=env, timeout=7200)

    # Stage this build's own native runtime and wheel; reject a substituted wheel.
    libs = sorted(config_dir.glob('libonnxruntime.so*'))
    if not libs:
        raise RuntimeError('no built libonnxruntime.so under ' + str(config_dir))
    wheels = sorted((config_dir / 'dist').glob('*.whl'))
    if not wheels:
        raise RuntimeError('no wheel produced under ' + str(config_dir / 'dist'))
    wheel = wheels[0]
    if wheel.stat().st_size < (1 << 20):
        raise RuntimeError('built wheel looks truncated, refusing to ship: ' + str(wheel))
    staged_wheel = session.output / wheel.name
    shutil.copy2(wheel, staged_wheel)
    (session.install / 'lib').mkdir(parents=True, exist_ok=True)
    for lib in libs:
        shutil.copy2(lib, session.install / 'lib' / lib.name)
    shutil.copy2(staged_wheel, session.install / wheel.name)

    # Fresh consumer environment, fully offline install of the newly built wheel.
    venv = session.consumer / 'venv'
    if venv.exists():
        shutil.rmtree(venv)
    session.run([sys.executable, '-m', 'venv', str(venv)], cwd=session.consumer,
                phase='package', name='consumer_venv')
    pip = str(venv / 'bin' / 'pip')
    session.run([pip, 'install', '--no-index', '--find-links', str(WHEELHOUSE), '--no-deps', str(staged_wheel)],
                cwd=session.consumer, phase='package', name='install_new_wheel')
    session.run([pip, 'install', '--no-index', '--find-links', str(WHEELHOUSE)] + CONSUMER_REQUIREMENTS,
                cwd=session.consumer, phase='package', name='install_consumer_deps')

    consumer = Path(__file__).resolve().parent / 'consumer_ort.py'
    session.run([str(venv / 'bin' / 'python'), str(consumer),
                 '--report', str(session.output / 'consumer_report.json')],
                cwd=session.consumer, phase='consumer', name='consume_ort_graph', timeout=900)

    session.finish(features={
        'wheel': staged_wheel.name, 'wheel_sha256': sha256(staged_wheel),
        'native_libraries': [lib.name for lib in libs], 'shared_lib_built': True,
        'execution_provider': 'CPUExecutionProvider',
        'official_tests': ['onnxruntime_test_all', 'onnxruntime_shared_lib_test'],
        'prepared_dependencies': len(prepared_dirs),
        'fetchcontent_source_dir_defines': len(defines),
        'declared_fetchcontent_names': len(declared),
        'cmake_extra_define_style': 'raw NAME=VALUE (build.sh adds -D)',
        'cmake_dir': str(cmake_dir),
        'cmake_version': '.'.join(str(p) for p in cmake_ver),
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
