#!/usr/bin/env python3
"""Build esbuild core profile: native CLI, official Go tests, independent CLI consumer."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from buildkit import Session, digest

REQUIRED_ARCHIVE_FILES = [
    'Makefile',
    'go.mod',
    'version.txt',
    'cmd/esbuild/main.go',
    'scripts/esbuild.js',
]


def parse_go_directive(text):
    match = re.search(r'(?m)^go\s+(\d+\.\d+\.\d+)', text)
    return match.group(1) if match else None


def version_tuple(value):
    return tuple(int(part) for part in re.findall(r'\d+', value)[:3])


def read_go_mod(tf):
    for member in tf.getmembers():
        parts = Path(member.name).parts
        if len(parts) == 2 and parts[1] == 'go.mod':
            stream = tf.extractfile(member)
            if stream is None:
                return None
            return parse_go_directive(stream.read().decode('utf-8', 'replace'))
    return None


def archive_has_file(tf, required):
    target = Path(required)
    for member in tf.getmembers():
        parts = Path(member.name).parts
        if len(parts) >= 2 and Path(*parts[1:]) == target:
            return True
    return False


def missing_items(input_dir):
    problems = []
    inp = Path(input_dir)
    if not inp.is_dir():
        return [f'missing input directory: {inp}']

    manifest_path = inp / 'manifest.json'
    if not manifest_path.is_file():
        return [f'missing manifest: {manifest_path}']
    manifest = json.loads(manifest_path.read_text())
    source = manifest.get('source', {})
    filename = source.get('filename', 'source.tar.gz')
    archive = inp / filename
    go_required = None

    if not archive.is_file():
        problems.append(f'missing source archive: {archive}')
    else:
        expected = source.get('sha256')
        if expected and digest(archive) != expected:
            problems.append(f'source archive sha256 mismatch: {archive}')
        else:
            try:
                with tarfile.open(archive) as tf:
                    for required in REQUIRED_ARCHIVE_FILES:
                        if not archive_has_file(tf, required):
                            problems.append(f'missing source file in archive: {required}')
                    go_required = read_go_mod(tf)
            except Exception as exc:
                problems.append(f'unreadable source archive: {archive}: {exc}')

    for tool in ['make', 'go', 'node']:
        if shutil.which(tool) is None:
            problems.append(f'missing tool: {tool}')

    go_bin = shutil.which('go')
    if go_bin:
        try:
            completed = subprocess.run([go_bin, 'version'], capture_output=True, text=True, timeout=30, check=False)
            version_text = (completed.stdout or completed.stderr).strip()
            match = re.search(r'go(\d+\.\d+(?:\.\d+)?)', version_text)
            if not match:
                problems.append(f'cannot determine Go version from: {version_text}')
            elif go_required and version_tuple(match.group(1)) < version_tuple(go_required):
                problems.append(f'go>={go_required} required by go.mod (found go{match.group(1)})')
        except Exception as exc:
            problems.append(f'cannot run go version: {exc}')

    return problems


def copy_consumer_template(destination):
    source = Path(__file__).resolve().parent / 'consumer'
    if not source.is_dir():
        raise RuntimeError(f'missing consumer template: {source}')
    shutil.copytree(source, destination, dirs_exist_ok=True)


def run_consumer(session):
    project = session.consumer / 'cli-project'
    if project.exists():
        shutil.rmtree(project)
    project.mkdir(parents=True)
    copy_consumer_template(project)
    binary = str(session.install / 'bin' / 'esbuild')

    session.run([binary, '--version'], cwd=project, phase='consumer', name='consumer-version', timeout=120)

    session.run(
        [binary, '--bundle', 'src/index.ts', '--platform=node', '--format=cjs', '--outfile=dist/out.js', '--metafile=dist/meta.json'],
        cwd=project, phase='consumer', name='consumer-bundle-ts', timeout=300,
    )
    execute_log = session.run(['node', 'dist/out.js'], cwd=project, phase='consumer', name='consumer-execute-bundle', timeout=120)
    execute_text = execute_log.read_text(errors='replace')
    if 'consumer ok math 42' not in execute_text:
        raise RuntimeError(f'unexpected consumer output: {execute_text!r}')

    metafile = json.loads((project / 'dist' / 'meta.json').read_text())
    inputs = set(metafile.get('inputs', {}))
    if not any(key.endswith('src/index.ts') for key in inputs):
        raise RuntimeError(f'metafile missing src/index.ts: {sorted(inputs)}')
    if not any(key.endswith('src/math.ts') for key in inputs):
        raise RuntimeError(f'metafile missing src/math.ts: {sorted(inputs)}')

    bad_log = session.run(
        [binary, 'src/invalid.ts', '--bundle', '--outfile=dist/bad.js'],
        cwd=project, phase='consumer', name='consumer-invalid-syntax', timeout=120, check=False,
    )
    if session.commands[-1]['exit_code'] == 0:
        raise RuntimeError('invalid syntax unexpectedly succeeded')
    if 'error' not in bad_log.read_text(errors='replace').lower():
        raise RuntimeError('invalid syntax did not report an error')

    miss_log = session.run(
        [binary, 'src/missing.ts', '--bundle', '--outfile=dist/missing.js'],
        cwd=project, phase='consumer', name='consumer-missing-import', timeout=120, check=False,
    )
    if session.commands[-1]['exit_code'] == 0:
        raise RuntimeError('missing import unexpectedly succeeded')
    if 'Could not resolve' not in miss_log.read_text(errors='replace'):
        raise RuntimeError('missing import did not report resolution failure')


def run(args):
    problems = missing_items(args.input)
    if problems:
        print(json.dumps({'ready': False, 'missing': problems}, ensure_ascii=False, indent=2))
        return 78

    session = Session(args.input, args.output, jobs=args.jobs)
    session.prepare()

    build_env = {
        'GOCACHE': str(session.build / 'go-cache'),
        'GOPATH': str(session.build / 'go-path'),
        'GOTOOLCHAIN': 'local',
        'GOPROXY': 'off',
        'GOMAXPROCS': str(session.jobs),
        'GOFLAGS': f'-p={session.jobs}',
        'CGO_ENABLED': '0',
    }
    test_env = dict(build_env, GOMAXPROCS='2', GOFLAGS='-p=2')

    session.run(['make', 'esbuild'], cwd=session.src, phase='build', name='make-esbuild', env=build_env, timeout=3600)
    binary = session.src / 'esbuild'
    if not binary.is_file():
        raise RuntimeError('make esbuild did not produce the esbuild binary')
    session.run([str(binary), '--version'], cwd=session.src, phase='verify', name='esbuild-version', env=build_env, timeout=120)

    install_bin = session.install / 'bin' / 'esbuild'
    install_bin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, install_bin)
    install_bin.chmod(0o755)
    license_path = session.src / 'LICENSE.md'
    if license_path.is_file():
        shutil.copy2(license_path, session.install / 'LICENSE.md')

    session.run(
        ['go', 'test', '-list=.', './internal/...', './pkg/...'],
        cwd=session.src, phase='test_discovery', name='go-test-list', env=test_env, timeout=1800,
    )
    session.test('make-test-go', ['make', 'test-go'], cwd=session.src, parser='auto', env=test_env, timeout=7200)
    run_consumer(session)

    session.finish(features={
        'profile': 'core',
        'native_cli': True,
        'official_test': 'make test-go',
        'independent_cli_consumer': True,
    })
    return 0


def doctor(args):
    problems = missing_items(args.input)
    print(json.dumps({'ready': not problems, 'missing': problems}, ensure_ascii=False, indent=2))
    return 78 if problems else 0


def main():
    parser = argparse.ArgumentParser(description='Build esbuild core profile from frozen source')
    subparsers = parser.add_subparsers(dest='command')

    doctor_parser = subparsers.add_parser('doctor', help='check whether source, tools, and dependencies are ready')
    doctor_parser.add_argument('--input', required=True)

    run_parser = subparsers.add_parser('run', help='build, test, install, and verify esbuild')
    run_parser.add_argument('--input', required=True)
    run_parser.add_argument('--output', required=True)
    run_parser.add_argument('--jobs', type=int, default=4)

    args = parser.parse_args()
    if args.command == 'doctor':
        return doctor(args)
    if args.command == 'run':
        return run(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
