#!/usr/bin/env python3
"""BUILDv1-B06 core-profile Ruby source builder (offline, gem-cache aware)."""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, os.environ.get('PYTHONPATH', ''))
import buildkit  # noqa: E402

TASK_ID = 'BUILDv1-B06'

TOOLS = ['gcc', 'make', 'autoconf', 'autoreconf', 'm4', 'bison', 'pkg-config', 'ruby', 'ld', 'objcopy']

LIBS = [
    ('zlib', ['zlib.h'], ['zlib']),
    ('openssl', ['openssl/ssl.h'], ['openssl', 'libssl']),
    ('yaml', ['yaml.h', 'libyaml/yaml.h'], ['yaml-0.1', 'yaml']),
    ('libffi', ['ffi.h', 'ffi/ffi.h'], ['libffi']),
    ('readline', ['readline/readline.h'], ['readline']),
    ('gdbm', ['gdbm.h'], ['gdbm']),
]

GEM_CACHE_ROOTS = ['/workspace/cache']


def _pkg_exists(names):
    for name in names:
        try:
            if subprocess.run(['pkg-config', '--exists', name],
                              capture_output=True, timeout=30).returncode == 0:
                return True
        except Exception:
            continue
    return False


def _header_exists(headers):
    for header in headers:
        for pattern in (f'/usr/include/{header}', f'/usr/local/include/{header}',
                        f'/usr/include/*/{header}', f'/usr/local/include/*/{header}',
                        f'/opt/*/include/{header}', f'/opt/*/include/*/{header}',
                        f'/opt/*/*/include/{header}', f'/opt/*/*/include/*/{header}',
                        f'/opt/*/*/*/include/{header}'):
            if glob.glob(pattern):
                return True
    return False


def _parse_bundled_gems(text):
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) >= 2:
            entries.append((parts[0], parts[1]))
    return entries


def _read_tar_member(archive, suffix):
    try:
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith(suffix):
                    stream = tar.extractfile(member)
                    if stream is not None:
                        return stream.read().decode('utf-8', 'replace')
    except Exception:
        pass
    return ''


def bundled_gem_entries(input_dir, manifest=None):
    src_manifest = Path('/workspace/src/gems/bundled_gems')
    if src_manifest.is_file():
        return _parse_bundled_gems(src_manifest.read_text())
    if manifest is None:
        return []
    archive = Path(input_dir) / manifest['source']['filename']
    if not archive.is_file():
        return []
    return _parse_bundled_gems(_read_tar_member(archive, '/gems/bundled_gems'))


def gem_cache_roots(input_dir):
    roots = []
    for candidate in [*GEM_CACHE_ROOTS, str(input_dir), '/workspace/input', '/workspace/source']:
        path = Path(candidate)
        if path.is_dir() and str(path) not in roots:
            roots.append(str(path))
    return roots


def find_cached_gem(filename, roots):
    for root in roots:
        direct = Path(root) / filename
        if direct.is_file():
            return direct
        try:
            for found in Path(root).rglob(filename):
                if found.is_file():
                    return found
        except Exception:
            continue
    return None


def check_gems(input_dir, manifest):
    entries = bundled_gem_entries(input_dir, manifest)
    src_gems = Path('/workspace/src/gems')
    roots = gem_cache_roots(input_dir)
    missing = []
    for name, version in entries:
        filename = f'{name}-{version}.gem'
        if (src_gems / filename).is_file():
            continue
        if find_cached_gem(filename, roots) is not None:
            continue
        missing.append(f'gem:{filename}')
    return missing


def provision_gems(input_dir):
    src_gems = Path('/workspace/src/gems')
    if not src_gems.is_dir():
        return []
    entries = bundled_gem_entries(input_dir)
    roots = gem_cache_roots(input_dir)
    missing = []
    for name, version in entries:
        filename = f'{name}-{version}.gem'
        dest = src_gems / filename
        if dest.is_file():
            continue
        found = find_cached_gem(filename, roots)
        if found is not None:
            shutil.copyfile(found, dest)
            continue
        missing.append(filename)
    return missing


def find_missing(input_dir):
    missing = []
    input_path = Path(input_dir).resolve()
    manifest_path = input_path / 'manifest.json'
    if not manifest_path.is_file():
        missing.append(f'source:manifest.json missing at {manifest_path}')
        return missing, None
    manifest = json.loads(manifest_path.read_text())
    archive = input_path / manifest['source']['filename']
    if not archive.is_file():
        missing.append(f'source:archive missing at {archive}')
    else:
        got = buildkit.digest(archive)
        if got != manifest['source']['sha256']:
            missing.append(f'source:sha256 mismatch for {archive}: '
                           f'expected {manifest["source"]["sha256"]}, got {got}')
    for tool in TOOLS:
        if shutil.which(tool) is None:
            missing.append(f'tool:{tool}')
    ruby = shutil.which('ruby')
    if ruby is not None:
        try:
            proc = subprocess.run([ruby, '-e', 'print RUBY_VERSION'],
                                  capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                missing.append('tool:ruby:cannot execute bootstrap ruby')
            else:
                version = proc.stdout.strip()
                try:
                    major, minor = (int(x) for x in version.split('.')[:2])
                    if (major, minor) < (2, 7):
                        missing.append(f'tool:ruby:version {version} is too old (need >= 2.7)')
                except Exception:
                    missing.append(f'tool:ruby:unparseable version {version!r}')
        except Exception as exc:
            missing.append(f'tool:ruby:probe failed: {exc}')
    for label, headers, pc_names in LIBS:
        if not _pkg_exists(pc_names) and not _header_exists(headers):
            missing.append(f'dependency:{label} (pkg-config names {pc_names} '
                           f'and headers {headers} not found)')
    missing.extend(check_gems(input_path, manifest))
    return missing, manifest


def cmd_doctor(args):
    missing, _ = find_missing(args.input)
    if missing:
        for item in missing:
            print(f'MISSING: {item}')
        return 78
    print('READY')
    return 0


def cmd_run(args):
    session = buildkit.Session(args.input, args.output, args.jobs)
    session.prepare()
    src = session.src
    build = session.build
    install = session.install
    output = session.output
    jobs = session.jobs

    missing_gems = provision_gems(args.input)
    if missing_gems:
        raise RuntimeError(
            'bundled gem cache is incomplete; run doctor to list exact items. '
            f'Missing: {missing_gems}')

    inventory = []
    for rel in ['test/ruby/test_string.rb', 'basictest/test.rb', 'gems/bundled_gems']:
        path = src / rel
        if path.is_file():
            inventory.append({'path': rel, 'bytes': path.stat().st_size,
                              'sha256': buildkit.digest(path)})
    session.write('test_inventory.json', inventory)

    session.run(['./autogen.sh'], cwd=src, phase='autogen', name='autogen', timeout=1800)

    configure = (src / 'configure').resolve()
    if not configure.is_file():
        raise RuntimeError(f'autogen did not produce {configure}')

    build_env = {'MAKEFLAGS': f'-j{jobs}'}
    session.run([
        str(configure),
        f'--prefix={install}',
        '--disable-install-doc',
        '--disable-install-rdoc',
        '--disable-yjit',
        '--disable-rjit',
    ], cwd=build, phase='configure', name='configure', env=build_env, timeout=1800)

    session.run(['make', '-j', str(jobs)], cwd=build, phase='build', name='make', env=build_env, timeout=7200)

    test_env = {'MAKEFLAGS': f'-j{jobs}', 'TEST_JOBS': '2'}
    session.test('make_test', ['make', 'test'], cwd=build, parser='auto', env=test_env, timeout=3600)
    string_test = (src / 'test' / 'ruby' / 'test_string.rb').resolve()
    if not string_test.is_file():
        raise RuntimeError(f'core test file missing: {string_test}')
    session.test('make_test_all_string',
                 ['make', 'test-all', f'TESTS={string_test}'],
                 cwd=build, parser='ruby_cases', env=test_env, timeout=3600)

    session.run(['make', 'install'], cwd=build, phase='install', name='make_install', env=build_env, timeout=1800)

    consumer = Path('/workspace/consumer')
    consumer.mkdir(parents=True, exist_ok=True)
    solution_dir = Path(__file__).resolve().parent
    for name in ['consumer_app.rb', 'rbconfig_report.rb', 'gem_manifest.rb']:
        shutil.copyfile(solution_dir / 'consumer' / name, consumer / name)

    ruby = install / 'bin' / 'ruby'
    if not ruby.is_file():
        raise RuntimeError(f'installed ruby not found at {ruby}')

    session.run([str(ruby), str(consumer / 'rbconfig_report.rb'), str(output / 'rbconfig.json')],
                cwd=consumer, phase='consumer', name='rbconfig', timeout=600)
    session.run([str(ruby), str(consumer / 'gem_manifest.rb'), str(output / 'default_gems.json')],
                cwd=consumer, phase='consumer', name='gem_manifest', timeout=600)
    session.run([str(ruby), str(consumer / 'consumer_app.rb')],
                cwd=consumer, phase='consumer', name='consumer_app', timeout=600)

    rb = json.loads((output / 'rbconfig.json').read_text())
    features = {
        'ruby_version': rb.get('ruby_version'),
        'patchlevel': rb.get('patchlevel'),
        'prefix': rb.get('prefix'),
        'extension_count': len(rb.get('extensions', [])),
        'test_selectors': ['make test', f'make test-all TESTS={string_test}'],
        'bundled_gem_source': 'offline cache provisioned into src/gems',
    }
    session.write('consumer_report.json', features)
    session.finish(features)

    src_tar = output / 'install.tar.gz'
    dst_tar = output / 'ruby-install.tar.gz'
    if src_tar.is_file():
        shutil.copyfile(src_tar, dst_tar)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Build Ruby interpreter and selected default extensions (BUILDv1-B06 core profile).')
    sub = parser.add_subparsers(dest='command')
    doctor = sub.add_parser('doctor', help='check source, tools and dependencies')
    doctor.add_argument('--input', required=True, help='read-only input directory')
    run = sub.add_parser('run', help='extract, build, test, install and verify')
    run.add_argument('--input', required=True, help='read-only input directory')
    run.add_argument('--output', required=True, help='writable output directory')
    run.add_argument('--jobs', type=int, default=4, help='build jobs (<=4)')
    args = parser.parse_args()
    if args.command == 'doctor':
        return cmd_doctor(args)
    if args.command == 'run':
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
