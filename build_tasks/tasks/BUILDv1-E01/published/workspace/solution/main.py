#!/usr/bin/env python3
"""BUILDv1-E01 (core profile): offline build of the Apache Kafka clients JAR,
the official RequestResponseTest selection, and an independent protocol
serialization consumer that loads the freshly installed JAR.

Frozen scope: clients JAR only. No broker, no release tarball, no Docker.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import buildkit

WORK = Path('/workspace')
SRC = WORK / 'src'
BUILD = WORK / 'build'
CONSUMER = WORK / 'consumer'
GRADLE_USER_HOME = BUILD / 'gradle-home'
PROBE_HOME = Path('/tmp/gradle-doctor-probe')
EXPECTED_VERSION = '3.9.1'
JAR_PREFIX = 'kafka-clients'
PROTOCOL_CONSUMER = 'KafkaProtocolRoundTrip'


def _probe(argv, env=None, timeout=180):
    proc_env = os.environ.copy()
    proc_env.update(env or {})
    try:
        proc = subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                              timeout=timeout, env=proc_env)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.returncode, (proc.stdout or '') + (proc.stderr or '')


def _item(name, ok, detail, required=True, provide=''):
    return {'name': name, 'ok': bool(ok), 'required': bool(required),
            'detail': detail, 'how_to_provide': provide}


def find_java():
    candidates = []
    if os.environ.get('JAVA_HOME'):
        candidates.append(Path(os.environ['JAVA_HOME']) / 'bin' / 'java')
    found = shutil.which('java')
    if found:
        candidates.append(Path(found))
    for exe in candidates:
        if not exe.is_file():
            continue
        probed = _probe([exe, '-version'])
        if not probed:
            continue
        match = re.search(r'version "(\d+)', probed[1])
        if match:
            return exe, int(match.group(1)), probed[1].strip().splitlines()[0]
    return None, None, 'no usable java executable on JAVA_HOME or PATH'


def gradle_candidates():
    out = []
    for var in ('KAFKA_GRADLE_HOME', 'GRADLE_HOME'):
        if os.environ.get(var):
            out.append(Path(os.environ[var]))
    out += [Path('/opt/gradle'), Path('/usr/share/gradle'), Path('/usr/local/gradle')]
    if Path('/opt').is_dir():
        out += sorted(Path('/opt').glob('gradle*'))
    homes = [os.environ.get('GRADLE_USER_HOME'), str(Path.home() / '.gradle')]
    for home in homes:
        if home and Path(home, 'wrapper', 'dists').is_dir():
            out += sorted(Path(home, 'wrapper', 'dists').glob('*/*/gradle-*/bin/gradle'))
    found = shutil.which('gradle')
    if found:
        out.append(Path(found))
    return out


def find_gradle(required):
    for candidate in gradle_candidates():
        exe = candidate / 'bin' / 'gradle' if candidate.is_dir() else candidate
        if not exe.is_file() or not os.access(str(exe), os.X_OK):
            continue
        probed = _probe([exe, '--version'], env={'GRADLE_USER_HOME': str(PROBE_HOME)})
        if not probed:
            continue
        match = re.search(r'Gradle\s+(\d+\.\d+(?:\.\d+)?)', probed[1])
        version = match.group(1) if match else 'unknown'
        if required and match and version.split('.')[0] != required.split('.')[0]:
            continue
        return exe, version
    return None, None


def dep_cache_candidates():
    out = []
    for var in ('GRADLE_RO_DEP_CACHE', 'KAFKA_GRADLE_CACHE', 'KAFKA_DEP_CACHE', 'GRADLE_DEP_CACHE'):
        if os.environ.get(var):
            out.append(Path(os.environ[var]))
    out += [Path('/opt/gradle-cache'), Path('/opt/gradle-caches'), Path('/opt/gradle-deps'),
            Path('/opt/deps/gradle'), Path('/workspace/input/gradle-cache')]
    if Path('/opt').is_dir():
        out += sorted(Path('/opt').glob('*gradle*cache*'))
        out += sorted(Path('/opt').glob('*gradle*repo*'))
    if os.environ.get('GRADLE_USER_HOME'):
        out.append(Path(os.environ['GRADLE_USER_HOME']))
    out.append(Path.home() / '.gradle' / 'caches')
    return out


def find_dep_cache():
    for candidate in dep_cache_candidates():
        for base in (candidate, candidate / 'caches'):
            try:
                if (base / 'modules-2').is_dir():
                    return base
            except OSError:
                continue
    return None


def cache_jars(cache, patterns):
    out = []
    if cache is None:
        return out
    for pattern in patterns:
        try:
            found = sorted(cache.glob('modules-2/files-2.1/*/*/*/*/' + pattern))
        except OSError:
            found = []
        if found:
            out.append(found[-1])
    return out


def wrapper_version(archive):
    try:
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                if member.name.endswith('gradle/wrapper/gradle-wrapper.properties'):
                    stream = tar.extractfile(member)
                    text = stream.read().decode('utf-8', 'replace') if stream else ''
                    match = re.search(r'gradle-(\d+\.\d+(?:\.\d+)?)-bin\.zip', text)
                    return match.group(1) if match else None
    except (OSError, tarfile.TarError):
        return None
    return None


def workspace_writable():
    try:
        BUILD.mkdir(parents=True, exist_ok=True)
        probe = BUILD / '.doctor-probe'
        probe.write_text('ok')
        probe.unlink()
        return True, str(BUILD)
    except OSError as exc:
        return False, 'workspace not writable: %s' % exc


def collect(input_dir):
    inp = Path(input_dir)
    items = []
    manifest = None
    manifest_path = inp / 'manifest.json'
    if not manifest_path.is_file():
        items.append(_item('input/manifest.json', False, 'missing %s' % manifest_path,
                           provide='mount the frozen task manifest next to the source archive'))
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
            items.append(_item('input/manifest.json', True,
                               'task_id=%s profile=%s' % (manifest.get('task_id'), manifest.get('profile'))))
        except (OSError, ValueError) as exc:
            items.append(_item('input/manifest.json', False, 'unparsable: %s' % exc))
    required_gradle = None
    if manifest:
        archive = inp / manifest['source']['filename']
        if not archive.is_file():
            items.append(_item('source archive', False, 'missing %s' % archive,
                               provide=manifest['source']['acquisition_url']))
        else:
            actual = buildkit.digest(archive)
            expected = manifest['source']['sha256']
            items.append(_item('source archive sha256', actual == expected,
                               'sha256=%s expected=%s' % (actual, expected)))
            required_gradle = wrapper_version(archive)
    items.append(_item('gradle wrapper version', required_gradle is not None,
                       'gradle-wrapper.properties declares %s' % (required_gradle or 'unknown'),
                       required=False,
                       provide='the frozen source archive must contain gradle/wrapper/gradle-wrapper.properties'))
    exe, major, message = find_java()
    items.append(_item('jdk', bool(exe) and major is not None and major >= 11,
                       ('%s -> %s' % (exe, message)) if exe else message,
                       provide='OpenJDK 11/17/21 installed, JAVA_HOME or PATH set'))
    items.append(_item('javac', bool(exe) and (exe.parent / 'javac').is_file(),
                       ('javac %s' % (exe.parent / 'javac')) if exe else 'no jdk found',
                       provide='a full JDK (not a JRE)'))
    gradle_exe, gradle_version = find_gradle(required_gradle)
    items.append(_item('gradle binary', gradle_exe is not None,
                       'binary=%s version=%s wrapper_requires=%s' % (gradle_exe, gradle_version, required_gradle),
                       provide='install Gradle %s via GRADLE_HOME/KAFKA_GRADLE_HOME, /opt/gradle*, PATH, '
                               'or pre-populate $GRADLE_USER_HOME/wrapper/dists' % (required_gradle or 'matching')))
    cache = find_dep_cache()
    sample = cache_jars(cache, ['*.jar'])
    items.append(_item('offline gradle dependency cache', cache is not None and bool(sample),
                       'cache=%s sample=%s' % (cache, sample[0].name if sample else 'none'),
                       provide='pre-populate a Gradle dependency cache (modules-2) and point '
                               'GRADLE_RO_DEP_CACHE at it; the build host has no network'))
    writable, detail = workspace_writable()
    items.append(_item('writable workspace', writable, detail,
                       provide='mount /workspace writable (src, build, output, consumer)'))
    return items


def parse_junit(reports_dir):
    cases = []
    failures = 0
    skipped = 0
    reports = sorted(reports_dir.glob('TEST-*.xml')) if reports_dir.is_dir() else []
    for report in reports:
        root = ET.parse(report).getroot()
        for case in root.iter('testcase'):
            status = 'passed'
            if case.find('failure') is not None or case.find('error') is not None:
                status = 'failed'
                failures += 1
            elif case.find('skipped') is not None:
                status = 'skipped'
                skipped += 1
            cases.append({'suite': case.get('classname'), 'test': case.get('name'),
                          'status': status, 'time_s': float(case.get('time') or 0.0)})
    return {'source': 'clients/build/test-results/test/TEST-*.xml',
            'reports': [p.name for p in reports],
            'executed': len(cases), 'failures': failures, 'skipped': skipped, 'cases': cases}


def cmd_doctor(args):
    items = collect(args.input)
    blocking = [i for i in items if i['required'] and not i['ok']]
    report = {'task': 'BUILDv1-E01', 'mode': 'doctor',
              'input': str(Path(args.input).resolve()),
              'ready': not blocking, 'blocking_missing': blocking, 'checks': items}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not blocking else 78


def cmd_run(args):
    items = collect(args.input)
    blocking = [i for i in items if i['required'] and not i['ok']]
    if blocking:
        print(json.dumps({'task': 'BUILDv1-E01', 'mode': 'run', 'ready': False,
                          'blocking_missing': blocking}, indent=2, ensure_ascii=False))
        print('BUILDv1-E01: refusing to build, %d required item(s) missing' % len(blocking),
              file=sys.stderr)
        return 78

    session = buildkit.Session(args.input, args.output, args.jobs)
    manifest = session.manifest
    session.write('doctor.json', items)
    session.prepare()

    archive = session.input / manifest['source']['filename']
    required_gradle = wrapper_version(archive)
    gradle_exe, gradle_version = find_gradle(required_gradle)
    cache = find_dep_cache()
    java_exe, java_major, java_message = find_java()
    jobs = min(max(int(args.jobs), 1), 4)
    forks = min(max(jobs // 2, 1), 2)
    env = {'GRADLE_USER_HOME': str(GRADLE_USER_HOME),
           'GRADLE_RO_DEP_CACHE': str(cache),
           'JAVA_HOME': str(java_exe.parent.parent)}
    base = [str(gradle_exe), '--offline', '--no-daemon', '--no-build-cache', '--console=plain',
            '--max-workers=%d' % jobs,
            '-PmaxParallelForks=%d' % forks,
            '-PmaxScalacThreads=4', '-PskipSigning=true',
            '-PcommitId=%s' % manifest['source']['commit']]

    session.run(base + [':clients:jar'], phase='build', name='clients_jar', env=env, timeout=5400)
    session.test('clients:test --tests RequestResponseTest',
                 base + [':clients:test', '--tests', 'RequestResponseTest', '-PmaxTestRetries=0'],
                 env=env, timeout=3600)

    inventory = parse_junit(SRC / 'clients' / 'build' / 'test-results' / 'test')
    session.write('official_tests_inventory.json', inventory)
    if inventory['executed'] == 0:
        raise RuntimeError('official test selection executed zero cases')
    if inventory['failures']:
        raise RuntimeError('official test selection reported %d failures' % inventory['failures'])

    libs_dir = SRC / 'clients' / 'build' / 'libs'
    expected_jar = libs_dir / ('%s-%s.jar' % (JAR_PREFIX, EXPECTED_VERSION))
    if not expected_jar.is_file():
        rebuilt = [p for p in sorted(libs_dir.glob('%s-*.jar' % JAR_PREFIX))
                   if not any(tag in p.name for tag in ('sources', 'javadoc', 'test'))]
        if not rebuilt:
            raise RuntimeError('clients jar not produced under %s' % libs_dir)
        expected_jar = rebuilt[0]
    if expected_jar.stat().st_mtime < session.started - 60:
        raise RuntimeError('clients jar predates this session: %s' % expected_jar)
    clients_jar = session.install / 'lib' / expected_jar.name
    clients_jar.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(expected_jar, clients_jar)

    consumer_source = Path(__file__).resolve().parent / 'consumer' / (PROTOCOL_CONSUMER + '.java')
    target_source = CONSUMER / (PROTOCOL_CONSUMER + '.java')
    shutil.copyfile(consumer_source, target_source)
    classes = CONSUMER / 'classes'
    classes.mkdir(parents=True, exist_ok=True)
    extra = cache_jars(cache, ['slf4j-api-*.jar', 'zstd-jni-*.jar', 'lz4-java-*.jar', 'snappy-java-*.jar'])
    classpath = os.pathsep.join([str(clients_jar)] + [str(p) for p in extra])
    session.run([str(java_exe.parent / 'javac'), '-d', str(classes), '-cp', classpath, str(target_source)],
                cwd=CONSUMER, phase='consumer', name='javac_protocol_consumer', env=env, timeout=600)
    run_log = session.run([str(java_exe), '-cp', os.pathsep.join([str(classes), classpath]), PROTOCOL_CONSUMER],
                          cwd=CONSUMER, phase='consumer', name='run_protocol_consumer', env=env, timeout=600)
    text = run_log.read_text(errors='replace')
    if 'ROUNDTRIP_OK' not in text:
        raise RuntimeError('protocol consumer did not report ROUNDTRIP_OK')

    session.write('build_manifest.json', {
        'task_id': manifest['task_id'], 'profile': manifest['profile'],
        'source_commit': manifest['source']['commit'], 'release_ref': manifest['source']['release_ref'],
        'java': java_message, 'gradle_binary': str(gradle_exe), 'gradle_version': gradle_version,
        'gradle_wrapper_required': required_gradle, 'gradle_offline_dep_cache': str(cache),
        'build_jobs': jobs, 'test_forks': forks,
        'clients_jar': {'name': clients_jar.name, 'sha256': buildkit.digest(clients_jar),
                        'bytes': clients_jar.stat().st_size},
    })
    session.write('consumer_evidence.json', {
        'consumer': PROTOCOL_CONSUMER, 'source': str(target_source),
        'classpath': classpath, 'clients_jar': str(clients_jar),
        'clients_jar_sha256': buildkit.digest(clients_jar),
        'scope': 'wire round trip of generated protocol messages, negative truncated-payload case, '
                 'StringSerializer/StringDeserializer; no broker involved'})

    session.finish(features={
        'profile': manifest['profile'],
        'scope': 'clients-jar-only (no broker, no release tarball, no Docker)',
        'gradle_version': gradle_version,
        'official_test_selection': 'clients:test --tests RequestResponseTest',
        'official_test_cases_executed': inventory['executed'],
        'installed_clients_jar': clients_jar.name,
        'independent_consumer': PROTOCOL_CONSUMER,
    })
    print(json.dumps({'task': 'BUILDv1-E01', 'status': 'ok',
                      'test_cases_executed': inventory['executed'],
                      'installed_jar': str(clients_jar)}, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='main.py',
        description='BUILDv1-E01 (core profile): build the Apache Kafka clients JAR offline, '
                    'run the official RequestResponseTest selection, and consume the installed JAR.')
    sub = parser.add_subparsers(dest='command')
    run_p = sub.add_parser('run', help='build, test, install and independently consume the clients JAR')
    run_p.add_argument('--input', default='/workspace/input')
    run_p.add_argument('--output', default='/workspace/output')
    run_p.add_argument('--jobs', type=int, default=4)
    doc = sub.add_parser('doctor', help='report missing source/tool/dependency items (exit 78 when not ready)')
    doc.add_argument('--input', default='/workspace/input')
    args = parser.parse_args(argv)
    if args.command == 'run':
        return cmd_run(args)
    if args.command == 'doctor':
        return cmd_doctor(args)
    parser.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
