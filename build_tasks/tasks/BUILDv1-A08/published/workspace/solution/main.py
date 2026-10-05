#!/usr/bin/env python3
"""PCRE2 core-profile builder: complete 8-bit library + POSIX wrapper + pcre2grep.

Frozen CORE scope (differs from the multi-width/JIT reference scope):
  * PCRE2_BUILD_PCRE2_8 = ON, 16/32 = OFF
  * PCRE2_SUPPORT_JIT   = OFF  (sljit submodule is intentionally not required)
  * Unicode enabled, official source test suites executed through CTest,
    pcre2grep built from this source tree and exercised as a functional consumer.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import buildkit

HERE = Path(__file__).resolve().parent


def _read(path):
    return Path(path).read_text(errors='replace')


def _manifest(input_dir):
    path = Path(input_dir) / 'manifest.json'
    return json.loads(path.read_text()) if path.is_file() else None


def pcre2_version(src):
    text = _read(Path(src) / 'configure.ac')
    major = re.search(r'pcre2_major,\s*\[(\d+)\]', text)
    minor = re.search(r'pcre2_minor,\s*\[(\d+)\]', text)
    return f'{major.group(1)}.{minor.group(1)}' if major and minor else None


def doctor(input_dir):
    missing = []
    inbox = Path(input_dir)
    manifest = _manifest(inbox)
    if manifest is None:
        missing.append(f'missing manifest: {inbox / "manifest.json"}')
    else:
        source = manifest.get('source', {})
        filename = source.get('filename')
        archive = inbox / str(filename)
        if not filename or not archive.is_file():
            missing.append(f'missing source archive: {archive}')
        else:
            try:
                got = buildkit.digest(archive)
            except OSError as exc:
                missing.append(f'unreadable source archive {archive}: {exc}')
            else:
                if got != source.get('sha256'):
                    missing.append(f'source archive sha256 mismatch: {got} != {source.get("sha256")}')
                if source.get('bytes') and archive.stat().st_size != source['bytes']:
                    missing.append(f'source archive size mismatch: {archive.stat().st_size}')
    for tool in ('cc', 'cmake', 'ninja'):
        if shutil.which(tool) is None:
            missing.append(f'missing build tool: {tool}')
    if missing:
        print('doctor: NOT READY (core profile)')
        for item in missing:
            print('  - ' + item)
        return 78
    print('doctor: READY (core profile: 8-bit library + POSIX wrapper + pcre2grep, '
          'JIT disabled; sljit submodule not required)')
    return 0


def _consumers(session, install, work, version):
    inc = install / 'include'
    lib = install / 'lib'
    for name in ('consumer8.c', 'consumer_posix.c'):
        shutil.copy(HERE / name, work / name)

    def compile_one(name, libs):
        exe = work / name
        session.run(['cc', '-O2', '-Wall', '-Wextra', f'-I{inc}', str(work / f'{name}.c'),
                     '-o', str(exe), f'-L{lib}', *libs],
                    cwd=work, phase='consumer_build', name=f'build_{name}', timeout=600)
        return exe

    exe8 = compile_one('consumer8', ['-lpcre2-8'])
    log8 = session.run([str(exe8)], cwd=work, phase='consumer_run', name='run_consumer8', timeout=300)
    text8 = _read(log8)
    lines = text8.splitlines()
    if 'CONSUMER8 OK' not in text8:
        raise RuntimeError('consumer8 failed:\n' + text8)
    if version and not any(line.startswith(f'VERSION={version}') for line in lines):
        raise RuntimeError(f'consumer8 linked a PCRE2 other than {version}:\n' + text8)
    if 'JIT=0' not in lines:
        raise RuntimeError('consumer8 expected JIT disabled:\n' + text8)
    if 'UNICODE=1' not in lines:
        raise RuntimeError('consumer8 expected Unicode enabled:\n' + text8)

    exe_posix = compile_one('consumer_posix', ['-lpcre2-posix', '-lpcre2-8'])
    logp = session.run([str(exe_posix)], cwd=work, phase='consumer_run', name='run_consumer_posix', timeout=300)
    if 'CONSUMER_POSIX OK' not in _read(logp):
        raise RuntimeError('consumer_posix failed:\n' + _read(logp))

    grep = install / 'bin' / 'pcre2grep'
    vlog = session.run([str(grep), '--version'], cwd=work, phase='consumer_grep',
                       name='pcre2grep_version', timeout=120)
    if version and version not in _read(vlog):
        raise RuntimeError('pcre2grep version mismatch:\n' + _read(vlog))

    data = work / 'grep_input.txt'
    data.write_text('alpha 1\nbeta 2\ngamma 3\nAlpha 4\n')
    glog = session.run([str(grep), '-n', '^[a-z]+ [0-9]$', str(data)], cwd=work,
                       phase='consumer_grep', name='pcre2grep_functional', timeout=300)
    got = _read(glog).splitlines()
    expected = ['1:alpha 1', '2:beta 2', '3:gamma 3']
    if got != expected:
        raise RuntimeError(f'pcre2grep output mismatch: got {got} expected {expected}')

    session.run([str(grep), '-q', 'ZZTOP_NOPE', str(data)], cwd=work, phase='consumer_grep_negative',
                name='pcre2grep_nomatch', check=False, timeout=300)
    code = session.commands[-1]['exit_code']
    if code != 1:
        raise RuntimeError(f'pcre2grep no-match exit code expected 1, got {code}')


def run(args):
    session = buildkit.Session(args.input, args.output, args.jobs)
    session.prepare()
    src, build, install, work = session.src, session.build, session.install, session.consumer
    version = pcre2_version(src)

    generator = ['-G', 'Ninja'] if shutil.which('ninja') else []
    session.run(['cmake', '-S', str(src), '-B', str(build), *generator,
                 '-DCMAKE_BUILD_TYPE=Release',
                 f'-DCMAKE_INSTALL_PREFIX={install}',
                 '-DPCRE2_BUILD_PCRE2_8=ON',
                 '-DPCRE2_BUILD_PCRE2_16=OFF',
                 '-DPCRE2_BUILD_PCRE2_32=OFF',
                 '-DPCRE2_SUPPORT_JIT=OFF',
                 '-DPCRE2_SUPPORT_UNICODE=ON',
                 '-DPCRE2_BUILD_TESTS=ON',
                 '-DPCRE2_BUILD_PCRE2GREP=ON',
                 '-DPCRE2GREP_SUPPORT_JIT=OFF',
                 '-DPCRE2_SHOW_REPORT=ON'],
                cwd=build, phase='configure', name='cmake_configure', timeout=1800)

    session.run(['cmake', '--build', str(build), '--parallel', str(session.jobs)],
                cwd=build, phase='build', name='cmake_build', timeout=7200)

    discovery = session.run(['ctest', '--test-dir', str(build), '-N'],
                            cwd=build, phase='test_discovery', name='ctest_discovery', timeout=600)
    inventory = _read(discovery)
    session.write('official_test_inventory.txt', inventory)
    names = re.findall(r'Test\s+#\d+:\s+(\S+)', inventory)

    test_jobs = str(min(2, session.jobs))
    session.test('official_ctest_all',
                 ['ctest', '--test-dir', str(build), '--output-on-failure', '--parallel', test_jobs],
                 cwd=build, parser='ctest_cases', timeout=5400)
    for name in names:
        session.test(name,
                     ['ctest', '--test-dir', str(build), '-R', f'^{name}$', '--output-on-failure'],
                     cwd=build, parser='ctest_cases', timeout=3600)

    session.run(['cmake', '--install', str(build)], cwd=build, phase='install',
                name='cmake_install', timeout=1800)

    required = [install / 'include' / 'pcre2.h',
                install / 'include' / 'pcre2posix.h',
                install / 'lib' / 'libpcre2-8.a',
                install / 'lib' / 'libpcre2-posix.a',
                install / 'bin' / 'pcre2grep']
    for path in required:
        if not path.exists():
            raise RuntimeError(f'missing expected installed artifact: {path}')

    _consumers(session, install, work, version)

    session.finish(features={
        'profile': 'core',
        'code_unit_widths': [8],
        'jit': False,
        'unicode': True,
        'posix_wrapper': True,
        'pcre2grep': True,
        'pcre2_version': version,
        'official_suites': names,
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='pcre2-core-builder',
        description='Build, test, install and verify PCRE2 core profile (8-bit, JIT off).')
    sub = parser.add_subparsers(dest='command', required=True)
    runner = sub.add_parser('run', help='configure, build, run official suites, install, verify consumers')
    runner.add_argument('--input', default='input')
    runner.add_argument('--output', default='output')
    runner.add_argument('--jobs', type=int, default=4)
    checker = sub.add_parser('doctor', help='inspect inputs and tools without building')
    checker.add_argument('--input', default='input')
    args = parser.parse_args(argv)

    if args.command == 'doctor':
        return doctor(args.input)
    try:
        return run(args)
    except RuntimeError as exc:
        print(f'build failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
