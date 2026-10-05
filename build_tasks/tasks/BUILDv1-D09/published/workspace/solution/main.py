#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit


def sha256(path):
    return buildkit.digest(path)


def find_nginx_tests(input_dir):
    inp = Path(input_dir)
    for p in inp.rglob('nginx-tests'):
        if p.is_dir():
            return ('dir', p)
    for p in inp.rglob('nginx-tests*.tar.gz'):
        if p.is_file():
            return ('tar', p)
    return (None, None)


def check_doctor(input_dir):
    missing = []
    inp = Path(input_dir)
    if not inp.is_dir():
        missing.append(f'input directory {input_dir}')
        return missing
    manifest_path = inp / 'manifest.json'
    if not manifest_path.exists():
        missing.append(f'manifest {manifest_path}')
        return missing
    manifest = json.loads(manifest_path.read_text())
    src = manifest.get('source', {})
    archive = inp / src.get('filename', 'source.tar.gz')
    if not archive.exists():
        missing.append(f'source archive {archive}')
    else:
        if src.get('sha256') and sha256(archive) != src['sha256']:
            missing.append(f'source archive checksum mismatch {archive}')
    for tool in ['cc', 'make', 'perl', 'prove', 'tar', 'sh']:
        if not shutil.which(tool):
            missing.append(f'tool {tool}')
    pcre_found = any(Path(h).exists() for h in [
        '/usr/include/pcre2.h', '/usr/include/pcre.h',
        '/usr/local/include/pcre2.h', '/usr/local/include/pcre.h',
    ])
    if not pcre_found:
        missing.append('PCRE headers (pcre2.h or pcre.h)')
    zlib_found = any(Path(h).exists() for h in ['/usr/include/zlib.h', '/usr/local/include/zlib.h'])
    if not zlib_found:
        missing.append('zlib headers (zlib.h)')
    kind, _ = find_nginx_tests(inp)
    if kind is None:
        missing.append('nginx-tests source (nginx-tests directory or nginx-tests*.tar.gz under input)')
    try:
        subprocess.run(['perl', '-MTest::More', '-e', '1'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        missing.append('Perl module Test::More')
    return missing


def run(args):
    missing = check_doctor(args.input)
    if missing:
        raise RuntimeError('missing dependencies: ' + '; '.join(missing))
    session = buildkit.Session(args.input, args.output, jobs=args.jobs)
    session.prepare()
    configure = session.src / 'auto' / 'configure'
    session.run([str(configure), f'--prefix={session.install}'],
                cwd=session.src, phase='configure', name='configure')
    session.run(['make', f'-j{session.jobs}'],
                cwd=session.src, phase='build', name='make')
    session.run(['make', 'install'],
                cwd=session.src, phase='install', name='make_install')
    inp = Path(args.input)
    kind, path = find_nginx_tests(inp)
    if kind is None:
        raise RuntimeError('nginx-tests not found in input')
    test_dir = session.build / 'nginx-tests'
    if test_dir.exists():
        shutil.rmtree(test_dir)
    if kind == 'dir':
        shutil.copytree(path, test_dir)
    else:
        test_dir.mkdir(parents=True)
        with tarfile.open(path) as tf:
            for member in tf.getmembers():
                parts = Path(member.name).parts
                if not parts or '..' in parts or Path(member.name).is_absolute():
                    continue
                if len(parts) == 1:
                    continue
                member.name = str(Path(*parts[1:]))
                tf.extract(member, test_dir, filter='data')
    env = {'TEST_NGINX_BINARY': str(session.install / 'sbin' / 'nginx')}
    session.test('nginx_tests_proxy_ssi',
                 ['prove', '-v', '-j', '2', 'proxy.t', 'ssi.t'],
                 cwd=test_dir, env=env, timeout=1800)
    consumer_script = Path(__file__).resolve().parent / 'consumer.py'
    if not consumer_script.exists():
        raise RuntimeError('consumer.py not found next to main.py')
    session.run(['python3', str(consumer_script),
                 '--nginx', str(session.install / 'sbin' / 'nginx'),
                 '--prefix', str(session.install),
                 '--workdir', str(session.consumer / 'run')],
                cwd=session.consumer, phase='consumer', name='consumer', timeout=600)
    session.finish(features={
        'profile': 'core',
        'configure': [f'--prefix={session.install}'],
        'official_tests': ['proxy.t', 'ssi.t'],
        'consumer': 'static+proxy+404+reload',
    })


def main():
    parser = argparse.ArgumentParser(prog='main.py')
    sub = parser.add_subparsers(dest='cmd')
    for cmd in ['run', 'doctor']:
        p = sub.add_parser(cmd)
        p.add_argument('--input', default='input')
        p.add_argument('--output', default='output')
        p.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if args.cmd == 'doctor':
        missing = check_doctor(args.input)
        if missing:
            print(json.dumps({'ready': False, 'missing': missing}, indent=2))
            return 78
        print(json.dumps({'ready': True, 'missing': []}))
        return 0
    if args.cmd == 'run':
        try:
            run(args)
        except Exception as exc:
            print(json.dumps({'ok': False, 'error': str(exc)}, indent=2))
            return 1
        return 0
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
