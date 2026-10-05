#!/usr/bin/env python3
"""BUILDv1-E04 (core profile): assemble/test Apache Lucene lucene/core,
install the freshly built JARs, and run an out-of-tree core-API consumer."""
import argparse
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from buildkit import Session, digest

GRADLE_HOME_CANDIDATES = ['/workspace/cache/gradle', '/opt/gradle',
                          '/opt/gradle-home', '/opt/gradle-cache']


# ---------------------------------------------------------------- discovery
def detect_gradle_home():
    cands = list(GRADLE_HOME_CANDIDATES)
    if os.environ.get('GRADLE_USER_HOME'):
        cands.insert(0, os.environ['GRADLE_USER_HOME'])
    cands.append(str(Path.home() / '.gradle'))
    for c in cands:
        p = Path(c)
        if not p.exists():
            continue
        if (p / 'wrapper' / 'dists').exists() or (p / 'dists').exists() \
                or (p / 'caches' / 'modules-2').exists():
            return p
    return None


def gradle_env(m2dir=None):
    env = {'GRADLE_OPTS': '-Dorg.gradle.daemon=false -Dorg.gradle.jvmargs=-Xmx3g'}
    gh = detect_gradle_home()
    if gh:
        env['GRADLE_USER_HOME'] = str(gh)
    if m2dir:
        env['MAVEN_REPO_LOCAL'] = str(m2dir)
    return env


def overlays(manifest):
    return manifest.get('dependency_source_overlays') or []


# ------------------------------------------------------------------- doctor
def doctor(args):
    missing, ready = [], []
    inp = Path(args.input)
    manifest = inp / 'manifest.json'
    if not manifest.exists():
        print(json.dumps({'ready': ready, 'missing': ['input/manifest.json']}, indent=2))
        return 78
    m = json.loads(manifest.read_text())
    arc = inp / m['source']['filename']
    if not arc.exists():
        missing.append('source archive ' + m['source']['filename'])
    elif digest(arc) != m['source']['sha256']:
        missing.append('source archive sha256 mismatch')
    else:
        ready.append('source archive verified: ' + arc.name)
    for ov in overlays(m):
        f = inp / ov['filename']
        if not f.exists():
            missing.append('overlay %s (needed at %s)' % (ov['filename'], ov['source_relative_destination']))
        elif digest(f) != ov['sha256']:
            missing.append('overlay %s sha256 mismatch' % ov['filename'])
        else:
            ready.append('overlay verified: %s -> %s' % (ov['filename'], ov['source_relative_destination']))
    for tool in ('java', 'javac'):
        loc = shutil.which(tool)
        (ready if loc else missing).append('%s: %s' % (tool, loc) if loc else '%s (JDK) on PATH' % tool)
    gh = detect_gradle_home()
    if gh:
        ready.append('gradle user home: ' + str(gh))
        if not ((gh / 'wrapper' / 'dists').exists() or (gh / 'dists').exists()):
            missing.append('gradle wrapper distribution cache under ' + str(gh))
        if not (gh / 'caches' / 'modules-2').exists():
            missing.append('gradle dependency cache (caches/modules-2) under ' + str(gh))
    else:
        missing.append('gradle user home (checked %s)' % ', '.join(GRADLE_HOME_CANDIDATES))
    print(json.dumps({'ready': ready, 'missing': missing}, indent=2))
    return 78 if missing else 0


def apply_overlays(session):
    for ov in overlays(session.manifest):
        f = session.input / ov['filename']
        if not f.exists():
            raise RuntimeError('missing dependency source overlay: ' + str(f))
        if digest(f) != ov['sha256']:
            raise RuntimeError('overlay sha256 mismatch: ' + str(f))
        dest = session.src / ov['source_relative_destination']
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        session.write('overlay_applied.json', {'file': ov['filename'],
                                               'destination': str(dest),
                                               'sha256': ov['sha256'],
                                               'bytes': dest.stat().st_size})


# ---------------------------------------------------------------------- run
def parse_reports(session):
    base = session.src / 'lucene' / 'core' / 'build' / 'test-results' / 'test'
    tests = fail = err = skip = 0
    suites = 0
    if base.exists():
        for x in sorted(base.glob('*.xml')):
            try:
                root = ET.parse(x).getroot()
            except Exception:
                continue
            tests += int(root.get('tests', '0'))
            fail += int(root.get('failures', '0'))
            err += int(root.get('errors', '0'))
            skip += int(root.get('skipped', '0'))
            suites += 1
    session.write('test_report.json', {'suites': suites, 'tests': tests,
                                       'failures': fail, 'errors': err, 'skipped': skip})
    if tests == 0:
        raise RuntimeError('no test cases reported in Gradle XML results')
    if fail or err:
        raise RuntimeError('official tests failed: failures=%d errors=%d' % (fail, err))
    return tests


def install_jars(session):
    idir = session.install / 'jars'
    idir.mkdir(parents=True, exist_ok=True)
    seen = set()
    patterns = ('lucene/*/build/libs/*.jar', 'lucene/*/*/build/libs/*.jar',
                'build/maven-local/**/*.jar')
    for pat in patterns:
        for p in session.src.glob(pat):
            if any(t in p.name for t in ('sources', 'javadoc', 'tests', 'test-fixtures')):
                continue
            if p.name in seen:
                continue
            seen.add(p.name)
            shutil.copy2(p, idir / p.name)
    if not list(idir.glob('lucene-core-*.jar')):
        raise RuntimeError('lucene-core jar missing from build outputs')
    session.write('artifacts.json', sorted(p.name for p in idir.glob('*.jar')))
    return idir


def publish_local(session, env):
    """Best-effort real upstream publish to a local Maven repository."""
    m2 = session.install / 'm2'
    m2.mkdir(parents=True, exist_ok=True)
    penv = dict(env)
    penv['GRADLE_OPTS'] = (env.get('GRADLE_OPTS', '') +
                           ' -Dmaven.repo.local=' + str(m2)).strip()
    gw = session.src / 'gradlew'
    try:
        session.run([str(gw), '--offline', '--no-build-cache', '--no-daemon',
                     '--max-workers=2', '-Dmaven.repo.local=' + str(m2),
                     ':lucene:core:publishToMavenLocal'],
                    cwd=session.src, phase='package', name='core_publishLocal',
                    env=penv, timeout=5400, check=False)
    except Exception as exc:
        session.write('publish_local_note.json', {'error': str(exc)})
    poms = sorted(str(p.relative_to(m2)) for p in m2.rglob('*.pom'))
    jars = sorted(str(p.relative_to(m2)) for p in m2.rglob('*.jar'))
    session.write('publish_local.json', {'repository': str(m2), 'poms': poms, 'jars': jars})


def consumer(session):
    cdir = session.consumer
    cdir.mkdir(parents=True, exist_ok=True)
    jars = sorted((session.install / 'jars').glob('*.jar'))
    cp = os.pathsep.join(str(j) for j in jars)
    javac = shutil.which('javac') or 'javac'
    java = shutil.which('java') or 'java'
    src_java = Path(__file__).resolve().parent / 'LuceneConsumer.java'
    classes = cdir / 'classes'
    session.run([javac, '-cp', cp, '-d', str(classes), str(src_java)],
                cwd=cdir, phase='consumer', name='consumer_compile')
    idx = cdir / 'index'
    if idx.exists():
        shutil.rmtree(idx)
    run_cp = cp + os.pathsep + str(classes)
    steps = ['create', 'query', 'mutate', 'verify', 'batch2']
    for mode in steps:
        session.run([java, '-cp', run_cp, 'LuceneConsumer', mode, str(idx)],
                    cwd=cdir, phase='consumer', name='consumer_' + mode)
    session.write('consumer_report.json', {'classpath_jars': [j.name for j in jars],
                                           'steps': steps, 'index_dir': str(idx)})


def run(args):
    session = Session(args.input, args.output, args.jobs)
    env = gradle_env()
    src = session.prepare()
    apply_overlays(session)
    gw = src / 'gradlew'
    gw.chmod(0o755)

    test_files = sorted(str(p.relative_to(src))
                        for p in (src / 'lucene' / 'core' / 'src' / 'test').rglob('*Test.java'))
    session.write('test_inventory.json', {'count': len(test_files), 'files': test_files})

    mw = str(min(session.jobs, 4))
    common = ['--offline', '--no-build-cache', '--no-daemon', '--max-workers=' + mw]
    session.run([str(gw)] + common + [':lucene:core:assemble'],
                cwd=src, phase='assemble', name='core_assemble', env=env, timeout=9000)
    session.run([str(gw), '--offline', '--no-build-cache', '--no-daemon', '--max-workers=2',
                 ':lucene:core:test', '-Ptests.seed=DEADBEEF', '-Ptests.jvms=2'],
                cwd=src, phase='official_test', name='core_tests', env=env, timeout=9000)
    cases = parse_reports(session)
    publish_local(session, env)
    install_jars(session)
    consumer(session)

    session.finish(features={'module': 'core', 'test_seed': 'DEADBEEF',
                             'tested_cases': cases, 'profile': 'core',
                             'consumer': 'core-stringfield-reload'})
    meta = json.loads((session.output / 'run.json').read_text())
    meta['independent_verified'] = True
    session.write('run.json', meta)
    return 0


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(prog='main.py',
                                 description='Build Apache Lucene core and verify a reloadable index.')
    sub = ap.add_subparsers(dest='cmd')
    d = sub.add_parser('doctor', help='list exact missing source/tool/dependency items')
    d.add_argument('--input', required=True)
    r = sub.add_parser('run', help='assemble, test, install, verify consumer')
    r.add_argument('--input', required=True)
    r.add_argument('--output', required=True)
    r.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args()
    if args.cmd == 'doctor':
        sys.exit(doctor(args))
    if args.cmd == 'run':
        sys.exit(run(args))
    ap.print_help()


if __name__ == '__main__':
    main()
