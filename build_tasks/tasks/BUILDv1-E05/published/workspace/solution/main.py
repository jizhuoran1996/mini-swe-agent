#!/usr/bin/env python3
"""BUILDv1-E05 (frozen CORE profile) task driver.

CORE scope only (differs from the reference instance):
  * build the :server JAR of Elasticsearch v8.17.6, not the whole localDistro;
  * run the frozen query-package unit test selection
    (org.elasticsearch.index.query.MatchQueryBuilderTests);
  * install the produced JAR into an out-of-tree INSTALL_ROOT and verify it with
    an independent Java artifact verifier (this is NOT a running service).

All build/test/install/consumer commands are dispatched through buildkit.Session
so exit codes and logs are preserved as formal evidence.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

from buildkit import Session, digest  # trusted execution helper


# --------------------------------------------------------------------------- #
# doctor                                                                      #
# --------------------------------------------------------------------------- #
def _java_major(java):
    if not java:
        return None
    try:
        proc = subprocess.run([java, '-version'], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r'version "(\d+)(?:\.(\d+))?', proc.stderr + proc.stdout)
    if not match:
        return None
    major = int(match.group(1))
    if major == 1 and match.group(2):
        major = int(match.group(2))
    return major


def _gradle_home():
    return Path(os.environ['GRADLE_USER_HOME']) if os.environ.get('GRADLE_USER_HOME') else (Path.home() / '.gradle')


def _archive_members(archive):
    with tarfile.open(archive) as handle:
        return handle.getnames()


def diagnose(input_dir):
    """Return a list of exact missing source/tool/dependency items."""
    missing = []
    input_dir = Path(input_dir)

    manifest_path = input_dir / 'manifest.json'
    manifest = None
    if not manifest_path.is_file():
        missing.append({'item': 'manifest.json', 'kind': 'source', 'detail': str(manifest_path)})
    else:
        manifest = json.loads(manifest_path.read_text())

    archive = None
    if manifest:
        archive = input_dir / manifest['source']['filename']
        if not archive.is_file():
            missing.append({'item': manifest['source']['filename'], 'kind': 'source', 'detail': str(archive)})
        elif digest(archive) != manifest['source']['sha256']:
            missing.append({'item': manifest['source']['filename'], 'kind': 'source', 'detail': 'sha256 mismatch'})

    for tool in ('java', 'javac', 'tar'):
        if shutil.which(tool) is None:
            missing.append({'item': tool, 'kind': 'tool', 'detail': 'not on PATH'})

    major = _java_major(shutil.which('java'))
    if major is None:
        if shutil.which('java'):
            missing.append({'item': 'java', 'kind': 'tool', 'detail': 'version not detectable'})
    elif major < 21:
        missing.append({'item': 'java>=21', 'kind': 'tool', 'detail': f'found java {major}'})

    if archive is not None and archive.is_file():
        try:
            names = set(_archive_members(archive))
            roots = {n.split('/', 1)[0] for n in names}
            root = next(iter(roots)) if roots else ''
            for rel in ('gradlew', 'gradle/wrapper/gradle-wrapper.jar',
                        'gradle/wrapper/gradle-wrapper.properties', 'server/build.gradle'):
                if f'{root}/{rel}' not in names:
                    missing.append({'item': rel, 'kind': 'source', 'detail': 'absent from source archive'})
        except tarfile.TarError as exc:
            missing.append({'item': 'source archive', 'kind': 'source', 'detail': f'unreadable: {exc}'})

    wrapper = _gradle_home() / 'wrapper' / 'dists'
    if not wrapper.is_dir() or not any(wrapper.iterdir()):
        missing.append({'item': 'gradle-wrapper-distribution', 'kind': 'dependency',
                        'detail': f'no Gradle distribution under {wrapper}; ./gradlew cannot run offline'})
    caches = _gradle_home() / 'caches' / 'modules-2'
    if not caches.is_dir():
        missing.append({'item': 'gradle-dependency-cache', 'kind': 'dependency',
                        'detail': f'no offline dependency cache under {caches}; --offline resolution will fail'})
    return missing


# --------------------------------------------------------------------------- #
# run                                                                         #
# --------------------------------------------------------------------------- #
def _build_env():
    env = {'GRADLE_USER_HOME': str(_gradle_home()), 'GRADLE_OPTS': '-Dorg.gradle.jvmargs=-Xmx4g'}
    if os.environ.get('JAVA_HOME'):
        env['JAVA_HOME'] = os.environ['JAVA_HOME']
    else:
        java = shutil.which('java')
        if java:
            env['JAVA_HOME'] = str(Path(java).resolve().parent.parent)
    return env


def execute(args):
    missing = diagnose(args.input)
    hard = [m for m in missing if m['kind'] == 'source']
    if hard:
        print(json.dumps({'status': 'missing-input', 'items': hard}, indent=2))
        return 78

    session = Session(args.input, args.output, args.jobs)
    session.prepare()

    consumer_src = Path(__file__).resolve().parent / 'java' / 'EsArtifactVerifier.java'
    consumer_dir = session.consumer / 'verify'
    consumer_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(consumer_src, consumer_dir / 'EsArtifactVerifier.java')

    env = _build_env()
    gradlew = str(session.src / 'gradlew')
    workers = max(1, min(int(args.jobs), 4))

    # 1) build the :server JAR only (CORE profile, not localDistro).
    session.run([gradlew, '--offline', '--no-daemon', '--no-build-cache', '--console=plain',
                 f'-Dorg.gradle.workers.max={workers}', ':server:jar'],
                cwd=session.src, phase='build', name='gradle_server_jar', env=env, timeout=7200)

    jars = sorted(p for p in (session.src / 'server' / 'build' / 'libs').glob('server-*.jar')
                  if not p.name.endswith(('-sources.jar', '-javadoc.jar')))
    if not jars:
        raise RuntimeError('server build produced no :server JAR under server/build/libs')
    server_jar = jars[-1]

    # 2) frozen query-package unit test selection (nonempty by construction).
    session.test('MatchQueryBuilderTests',
                 [gradlew, '--offline', '--no-daemon', '--no-build-cache', '--console=plain',
                  f'-Dorg.gradle.workers.max={min(2, workers)}',
                  ':server:test', '--tests', 'org.elasticsearch.index.query.MatchQueryBuilderTests',
                  '-Dtests.seed=DEADBEEF'],
                 cwd=session.src, env=env, timeout=3600)

    # 3) install the produced artifact into out-of-tree INSTALL_ROOT.
    session.install.mkdir(parents=True, exist_ok=True)
    installed = session.install / server_jar.name
    shutil.copy(server_jar, installed)
    (session.install / 'MODULE_SCOPE.txt').write_text(
        'core-scope: :server JAR + org.elasticsearch.index.query unit tests only; '\
        'this is a library artifact, not a running Elasticsearch service.\n')

    # 4) independent Java verification of the freshly built artifact.
    session.run(['javac', '-d', str(consumer_dir), str(consumer_dir / 'EsArtifactVerifier.java')],
                cwd=consumer_dir, phase='consumer', name='javac_verifier', env=env, timeout=300)
    session.run(['java', '-cp', str(consumer_dir), 'EsArtifactVerifier', str(installed)],
                cwd=consumer_dir, phase='consumer', name='java_verifier', env=env, timeout=300)

    manifest = json.loads((session.input / 'manifest.json').read_text())
    session.write('verify.json', {'server_jar': server_jar.name,
                                  'install_path': str(installed),
                                  'sha256': digest(installed),
                                  'scope': 'core (:server JAR + query unit tests)',
                                  'release_ref': manifest['source'].get('release_ref'),
                                  'not_a_full_service': True})
    session.finish(features={'scope': 'core', 'target': ':server:jar',
                             'tests': ['org.elasticsearch.index.query.MatchQueryBuilderTests'],
                             'consumer': 'solution/java/EsArtifactVerifier.java',
                             'full_distribution_built': False})
    print('BUILDv1-E05 core: built, tested, installed and verified ->', session.output)
    return 0


# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(prog='main.py',
                                     description='BUILDv1-E05 CORE: build Elasticsearch :server JAR, run query unit tests, verify artifact.')
    subs = parser.add_subparsers(dest='command')
    doc = subs.add_parser('doctor', help='report exact missing source/tool/dependency items (78 if missing)') 
    doc.add_argument('--input', required=True, help='read-only input dir containing manifest.json + source archive')
    run = subs.add_parser('run', help='build, test, install and independently verify')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)

    if args.command == 'doctor':
        missing = diagnose(args.input)
        print(json.dumps({'status': 'missing' if missing else 'ready',
                          'profile': 'core', 'items': missing}, ensure_ascii=False, indent=2))
        return 78 if missing else 0
    if args.command == 'run':
        return execute(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
