#!/usr/bin/env python3
"""BUILDv1-E02 (core profile).

Cold source build of the Spark 'core' Maven module plus its reactor
dependencies, official DAGSchedulerSuite run, and an independent local RDD
consumer launched from the newly built artifacts only.

Deployment fix: the delivered INSTALL_ROOT now contains the freshly built
Spark reactor JARs *and* the genuine external runtime dependency closure
staged by byte-hash (original names, exact bytes, deduplicated, collisions
detected). A relocatable classpath of the delivered files is written next to
them. The authored RDD consumer is compiled and launched exclusively against
those delivered files, with Spark's original JavaModuleOptions JVM flags
supplied explicitly (parsed from the unmodified upstream source), so no
--add-opens injection from spark-submit is required and no source tree or
Maven cache path is used at runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from buildkit import Session, digest

TASK_ID = 'BUILDv1-E02'
SPARK_VERSION = '3.5.7'
SUITE = 'org.apache.spark.scheduler.DAGSchedulerSuite'
SUITE_REL = 'core/src/test/scala/org/apache/spark/scheduler/DAGSchedulerSuite.scala'
MODULE_OPTIONS_REL = 'launcher/src/main/java/org/apache/spark/launcher/JavaModuleOptions.java'
SKIPS = [
    '-Dcheckstyle.skip=true',
    '-Drat.skip=true',
    '-Dscalastyle.skip=true',
    '-Dmaven.javadoc.skip=true',
]
HERE = Path(__file__).resolve().parent
LOG4J = (
    'rootLogger.level = warn\n'
    'rootLogger.appenderRef.stdout.ref = console\n'
    'appender.console.type = Console\n'
    'appender.console.name = console\n'
    'appender.console.layout.type = PatternLayout\n'
    'appender.console.layout.pattern = %d{HH:mm:ss} %p %c{1}: %m%n\n'
)


def maven_repo_candidates():
    out = []
    for key in ('MAVEN_REPOSITORY', 'MAVEN_REPO_LOCAL', 'MAVEN_LOCAL_REPO'):
        value = os.environ.get(key)
        if value:
            out.append(Path(value))
    out.append(Path('/workspace/cache/maven'))
    out.append(Path('/workspace/input/m2'))
    out.append(Path(os.environ.get('HOME', '/tmp')) / '.m2' / 'repository')
    out.append(Path('/opt/m2'))
    out.append(Path('/workspace/m2'))
    seen, unique = set(), []
    for candidate in out:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def pick_maven_repo():
    candidates = maven_repo_candidates()
    for candidate in candidates:
        if (candidate / 'org' / 'scala-lang').is_dir():
            return candidate
    return candidates[0]


def missing_items(input_dir):
    issues = []
    inp = Path(input_dir)
    manifest_path = inp / 'manifest.json'
    manifest = None
    if not manifest_path.is_file():
        issues.append(f'input manifest {manifest_path}')
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception as exc:  # noqa: BLE001
            issues.append(f'input manifest unreadable: {exc}')
    if manifest:
        source = manifest.get('source', {})
        archive = inp / source.get('filename', 'source.tar.gz')
        if not archive.is_file():
            issues.append(f'source archive {archive}')
        else:
            try:
                actual = digest(archive)
            except Exception as exc:  # noqa: BLE001
                issues.append(f'source archive unreadable: {exc}')
                actual = None
            if actual and source.get('sha256') and actual != source['sha256']:
                issues.append(f'source archive sha256 mismatch: {actual} != {source["sha256"]}')
    for tool in ('java', 'javac', 'mvn'):
        if shutil.which(tool) is None:
            issues.append(f'build tool not on PATH: {tool}')
    repo = pick_maven_repo()
    for marker in ('org/scala-lang', 'org/apache/hadoop', 'org/apache/logging/log4j', 'org/scalatest'):
        if not (repo / marker).is_dir():
            issues.append(f'offline Maven artifact group: {marker} (under {repo})')
    return issues


def build_env(repo):
    env = {
        'LC_ALL': 'C',
        'MAVEN_OPTS': '-Xmx4g -XX:MaxMetaspaceSize=1g',
        'MAVEN_REPOSITORY': str(repo),
        'MAVEN_REPO_LOCAL': str(repo),
    }
    if os.environ.get('JAVA_HOME'):
        env['JAVA_HOME'] = os.environ['JAVA_HOME']
    return env


def mvn_base(repo):
    return ['mvn', '-o', '-B', '-ntp', f'-Dmaven.repo.local={repo}']


def parse_java_module_options(src):
    """Read Spark's original JavaModuleOptions constants from unmodified source.

    The upstream class stores the exact Java 17 module flags Spark requires
    (including --add-opens=java.base/sun.nio.ch=ALL-UNNAMED, which fixes the
    StorageUtils$ -> sun.nio.ch.DirectBuffer IllegalAccessError).
    """
    path = src / MODULE_OPTIONS_REL
    if not path.is_file():
        raise RuntimeError('missing Spark JavaModuleOptions source: ' + str(path))
    text = path.read_text(errors='replace')
    options = []
    for match in re.finditer(r'"(--?[^"]*)"', text):
        value = match.group(1)
        if value not in options:
            options.append(value)
    if not options:
        raise RuntimeError('parsed no JVM module options from ' + str(path))
    return options


def stage_delivery(session, src, classpath_paths):
    """Stage freshly built reactor JARs + genuine runtime dependency closure.

    Exact bytes are deduplicated by SHA-256; two distinct files sharing a
    filename but not their bytes are a hard collision (they cannot coexist in
    the flat delivered jars directory).
    """
    dest = session.install / 'jars'
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    candidates = []
    for target in sorted(src.rglob('target')):
        if not target.is_dir():
            continue
        for jar in sorted(target.glob('*.jar')):
            name = jar.name
            if name.startswith('original-'):
                continue
            if name.endswith(('-tests.jar', '-sources.jar', '-javadoc.jar')):
                continue
            candidates.append(('reactor', jar))
    for entry in classpath_paths:
        path = Path(entry)
        if path.is_file() and path.suffix == '.jar':
            candidates.append(('dependency', path))

    by_sha = {}
    name_to_sha = {}
    delivered = []
    collisions = []
    for origin, path in candidates:
        sha = digest(path)
        name = path.name
        if sha in by_sha:
            continue
        previous = name_to_sha.get(name)
        if previous is not None and previous != sha:
            collisions.append({'name': name, 'sha_a': previous, 'sha_b': sha,
                               'source': str(path)})
            continue
        name_to_sha[name] = sha
        by_sha[sha] = name
        shutil.copy2(path, dest / name)
        delivered.append({'name': name, 'sha256': sha,
                          'bytes': path.stat().st_size, 'origin': origin,
                          'source': str(path)})
    if collisions:
        session.write('jar_collisions.json', collisions)
        raise RuntimeError('jar filename collisions with differing bytes: '
                           + ', '.join(c['name'] for c in collisions))
    return delivered


def delivered_classpath(session, delivered):
    ordered = sorted(delivered, key=lambda d: (0 if d['origin'] == 'reactor' else 1, d['name']))
    entries = [f"jars/{d['name']}" for d in ordered]
    (session.install / 'classpath.txt').write_text('\n'.join(entries) + '\n')
    return ordered, entries


def cmd_doctor(args):
    issues = missing_items(args.input)
    if issues:
        for item in issues:
            print(f'MISSING: {item}')
        return 78
    print(f'READY: source archive + tools + offline Maven repository {pick_maven_repo()}')
    return 0


def cmd_run(args):
    issues = missing_items(args.input)
    if issues:
        for item in issues:
            print(f'MISSING: {item}', file=sys.stderr)
        print('refusing to build: prerequisites missing', file=sys.stderr)
        return 78

    session = Session(args.input, args.output, args.jobs)
    repo = pick_maven_repo()
    base = mvn_base(repo)
    env = build_env(repo)
    src = session.prepare()

    pom = (src / 'pom.xml').read_text(errors='replace')
    if f'<version>{SPARK_VERSION}</version>' not in pom:
        raise SystemExit(f'unexpected source version (want {SPARK_VERSION})')

    # --- configure: capture exact toolchain ---
    session.run(base + ['-v'], cwd=src, phase='configure', name='mvn_version',
                env=env, timeout=300, check=False)
    session.run(['java', '-version'], cwd=src, phase='configure', name='java_version',
                env=env, timeout=300, check=False)

    # --- official test discovery + original launcher module options ---
    suite_file = src / SUITE_REL
    declared = len(re.findall(r'\n\s*test\("', suite_file.read_text(errors='replace'))) \
        if suite_file.is_file() else 0
    module_options = parse_java_module_options(src)
    session.write('test_inventory.json', {
        'selector': SUITE,
        'source': SUITE_REL,
        'source_present': suite_file.is_file(),
        'declared_test_cases': declared,
        'maven_repo_local': str(repo),
        'java_module_options': module_options,
    })

    # --- build: core plus reactor dependencies ---
    session.run(base + ['-pl', 'core', '-am', '-T', str(session.jobs),
                        '-DskipTests', *SKIPS, 'install'],
                cwd=src, phase='build', name='mvn_core_reactor_install',
                env=env, timeout=9000)

    # --- resolve the genuine runtime dependency closure offline ---
    cpfile = session.build / 'core-classpath.txt'
    session.run(base + ['-pl', 'core', '-DincludeScope=runtime',
                        'dependency:build-classpath', f'-Dmdep.outputFile={cpfile}'],
                cwd=src, phase='package', name='mvn_dependency_classpath',
                env=env, timeout=900)
    external = [p for p in cpfile.read_text().strip().split(os.pathsep)
                if p and p.endswith('.jar')]

    delivered = stage_delivery(session, src, external)
    ordered, cp_entries = delivered_classpath(session, delivered)
    reactor = [d for d in delivered if d['origin'] == 'reactor']
    if not any('spark-core' in d['name'] for d in reactor):
        raise RuntimeError('delivered set missing freshly built spark-core jar')
    session.write('delivery_report.json', {
        'delivered_jars': len(delivered),
        'reactor_jars': len(reactor),
        'dependency_jars': len(delivered) - len(reactor),
        'classpath_file': 'install/classpath.txt',
        'entries': cp_entries,
        'artifacts': delivered,
    })

    # --- official test: DAGSchedulerSuite (real source selector) ---
    session.test('DAGSchedulerSuite',
                 base + ['-pl', 'core', '-Dtest=none',
                         f'-DwildcardSuites={SUITE}', *SKIPS, 'test'],
                 cwd=src, env=env, timeout=5400)
    raw = (session.output / session.tests[-1]['raw_log']).read_text(errors='replace')
    total = re.search(r'Total number of tests run:\s*(\d+)', raw)
    split = re.search(r'Tests: succeeded (\d+), failed (\d+), canceled (\d+), ignored (\d+), pending (\d+)', raw)
    session.write('scalatest_report.json', {
        'selector': SUITE,
        'total_tests_run': int(total.group(1)) if total else None,
        'succeeded': int(split.group(1)) if split else None,
        'failed': int(split.group(2)) if split else None,
        'canceled': int(split.group(3)) if split else None,
        'ignored': int(split.group(4)) if split else None,
        'pending': int(split.group(5)) if split else None,
        'raw_log': session.tests[-1]['raw_log'],
    })

    # --- consumer: independent local RDD job from OUTSIDE the source tree ---
    cons = session.consumer
    classes = cons / 'classes'
    tmp = cons / 'tmp'
    for directory in (classes, tmp):
        directory.mkdir(parents=True, exist_ok=True)
    (classes / 'log4j2.properties').write_text(LOG4J)
    jsrc = cons / 'RddConsumer.java'
    shutil.copy2(HERE / 'consumer' / 'RddConsumer.java', jsrc)

    jars_dir = session.install / 'jars'
    delivered_paths = [str(jars_dir / d['name']) for d in ordered]
    cp_value = os.pathsep.join(delivered_paths)

    session.run(['javac', '-cp', cp_value, '-d', str(classes), str(jsrc)],
                cwd=cons, phase='consumer', name='javac_rdd_consumer',
                env=env, timeout=600)

    run_env = dict(env)
    run_env.update({'TMPDIR': str(tmp), 'SPARK_LOCAL_IP': '127.0.0.1',
                    'SPARK_LOCAL_DIRS': str(tmp)})
    positive_argv = ['java', *module_options, '-cp',
                     str(classes) + os.pathsep + cp_value, 'RddConsumer']
    run_log = session.run(positive_argv, cwd=cons, phase='consumer',
                          name='java_rdd_consumer_installed_only',
                          env=run_env, timeout=1800)
    text = run_log.read_text(errors='replace')
    if 'RDD_CONSUMER_OK' not in text:
        raise RuntimeError('RDD consumer did not report success')

    # --- negative: identical launch but delivered jars removed ---
    session.run(['java', *module_options, '-cp', str(classes), 'RddConsumer'],
                cwd=cons, phase='consumer', name='negative_missing_delivered_jars',
                env=run_env, timeout=600, check=False)
    negative = session.commands[-1]
    if negative['exit_code'] == 0:
        raise RuntimeError('negative consumer case unexpectedly succeeded')
    negative_log = (session.output / negative['log']).read_text(errors='replace')
    if 'NoClassDefFoundError' not in negative_log and 'ClassNotFoundException' not in negative_log:
        raise RuntimeError('negative consumer failed for an unexpected reason')

    session.write('consumer_report.json', {
        'kind': 'java-rdd-local-installed-only',
        'java_module_options': module_options,
        'positive_argv_tail': positive_argv[-2:],
        'delivered_jars': len(delivered_paths),
        'core_jar': next((d['name'] for d in reactor if 'spark-core' in d['name']), None),
        'positive_log': str(run_log.relative_to(session.output)),
        'negative_exit_code': negative['exit_code'],
        'negative_log': negative['log'],
    })

    session.finish({
        'profile': 'core',
        'module': 'core',
        'reactor_dependencies': True,
        'official_suite': SUITE,
        'delivered_jars': len(delivered),
        'reactor_jars': len(reactor),
        'dependency_jars': len(delivered) - len(reactor),
        'relocatable_classpath': 'install/classpath.txt',
        'consumer': 'java-rdd-local-installed-only',
        'java_module_options_source': MODULE_OPTIONS_REL,
    })
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='main.py',
                                     description='BUILDv1-E02 Spark core build/test/consumer harness')
    sub = parser.add_subparsers(dest='action')
    for name in ('run', 'doctor'):
        sp = sub.add_parser(name)
        sp.add_argument('--input', default='/workspace/input')
        if name == 'run':
            sp.add_argument('--output', default='/workspace/output')
            sp.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)
    if args.action == 'doctor':
        return cmd_doctor(args)
    if args.action == 'run':
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
