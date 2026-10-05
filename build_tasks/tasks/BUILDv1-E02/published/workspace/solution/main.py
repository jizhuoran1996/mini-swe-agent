#!/usr/bin/env python3
"""BUILDv1-E02 (core profile).

Build the Spark 'core' Maven module together with its reactor dependencies,
run the official DAGSchedulerSuite, install the produced JARs into an
isolated INSTALL_ROOT and run an independent local RDD consumer with the
newly built artifacts.
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
SCALA_BIN = '2.12'
SUITE = 'org.apache.spark.scheduler.DAGSchedulerSuite'
SUITE_REL = 'core/src/test/scala/org/apache/spark/scheduler/DAGSchedulerSuite.scala'
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
    if os.environ.get('MAVEN_REPO_LOCAL'):
        out.append(Path(os.environ['MAVEN_REPO_LOCAL']))
    out.append(Path(os.environ.get('HOME', '/root')) / '.m2' / 'repository')
    out.extend([Path('/opt/m2'), Path('/workspace/input/m2'), Path('/workspace/m2')])
    return out


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


def build_env():
    env = {
        'LC_ALL': 'C',
        'MAVEN_OPTS': '-Xmx4g -XX:MaxMetaspaceSize=1g',
    }
    if os.environ.get('JAVA_HOME'):
        env['JAVA_HOME'] = os.environ['JAVA_HOME']
    return env


def mvn_base(repo):
    return ['mvn', '-o', '-B', '-ntp', f'-Dmaven.repo.local={repo}']


def collect_installed_jars(session, src):
    dest = session.install / 'jars'
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for target in sorted(src.rglob('target')):
        if not target.is_dir():
            continue
        for jar in sorted(target.glob('*.jar')):
            name = jar.name
            if name.startswith('original-'):
                continue
            if name.endswith(('-tests.jar', '-sources.jar', '-javadoc.jar')):
                continue
            shutil.copy2(jar, dest / name)
            count += 1
    return count


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
    env = build_env()
    src = session.prepare()

    pom = (src / 'pom.xml').read_text(errors='replace')
    if f'<version>{SPARK_VERSION}</version>' not in pom:
        raise SystemExit(f'unexpected source version (want {SPARK_VERSION})')

    # --- configure: capture the exact toolchain that performs the build ---
    session.run(base + ['-v'], cwd=src, phase='configure', name='mvn_version',
                env=env, timeout=300, check=False)
    session.run(['java', '-version'], cwd=src, phase='configure', name='java_version',
                env=env, timeout=300, check=False)

    # --- official test discovery (before execution) ---
    suite_file = src / SUITE_REL
    declared = 0
    if suite_file.is_file():
        declared = len(re.findall(r'\n\s*test\("', suite_file.read_text(errors='replace')))
    session.write('test_inventory.json', {
        'selector': SUITE,
        'source': SUITE_REL,
        'source_present': suite_file.is_file(),
        'declared_test_cases': declared,
    })

    # --- build: core plus its reactor dependencies ---
    session.run(base + ['-pl', 'core', '-am', '-T', str(session.jobs),
                        '-DskipTests', *SKIPS, 'install'],
                cwd=src, phase='build', name='mvn_core_reactor_install',
                env=env, timeout=9000)
    count = collect_installed_jars(session, src)
    if count == 0:
        raise RuntimeError('reactor build produced no JARs to install')

    # --- official test: DAGSchedulerSuite ---
    session.test('DAGSchedulerSuite',
                 base + ['-pl', 'core', '-Dtest=none',
                         f'-DwildcardSuites={SUITE}', *SKIPS, 'test'],
                 cwd=src, env=env, timeout=5400)
    raw = (session.output / session.tests[-1]['raw_log']).read_text(errors='replace')
    total = re.search(r'Total number of tests run:\s*(\d+)', raw)
    split = re.search(r'Tests: succeeded (\d+), failed (\d+), canceled (\d+), ignored (\d+), pending (\d+)', raw)
    if total or split:
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

    # --- classpath for the consumer, resolved from the local repository ---
    cpfile = session.build / 'core-classpath.txt'
    session.run(base + ['-pl', 'core', '-DincludeScope=runtime',
                        'dependency:build-classpath', f'-Dmdep.outputFile={cpfile}'],
                cwd=src, phase='package', name='mvn_dependency_classpath',
                env=env, timeout=900)
    deps = [p for p in cpfile.read_text().strip().split(os.pathsep) if p]

    jars_dir = session.install / 'jars'
    own_jars = sorted(str(p) for p in jars_dir.glob('*.jar'))
    if not own_jars:
        raise RuntimeError('no installed JARs for consumer classpath')
    cp = os.pathsep.join(own_jars + deps)

    # --- consumer: independent local RDD job, built outside the source tree ---
    cons = session.consumer
    classes = cons / 'classes'
    tmp = cons / 'tmp'
    classes.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    (classes / 'log4j2.properties').write_text(LOG4J)
    jsrc = cons / 'RddConsumer.java'
    shutil.copy2(HERE / 'consumer' / 'RddConsumer.java', jsrc)

    session.run(['javac', '-cp', cp, '-d', str(classes), str(jsrc)],
                cwd=cons, phase='consumer', name='javac_rdd_consumer',
                env=env, timeout=600)

    run_cp = str(classes) + os.pathsep + cp
    run_env = dict(env)
    run_env.update({'TMPDIR': str(tmp), 'SPARK_LOCAL_IP': '127.0.0.1', 'SPARK_LOCAL_DIRS': str(tmp)})
    run_log = session.run(['java', '-cp', run_cp, 'RddConsumer'],
                          cwd=cons, phase='consumer', name='java_rdd_consumer',
                          env=run_env, timeout=1800)
    text = run_log.read_text(errors='replace')
    if 'RDD_CONSUMER_OK' not in text:
        raise RuntimeError('RDD consumer did not report success')

    # --- negative case: consumer must depend on the freshly built JARs ---
    session.run(['java', '-cp', str(classes), 'RddConsumer'],
                cwd=cons, phase='consumer', name='negative_missing_jars',
                env=run_env, timeout=300, check=False)
    if session.commands[-1]['exit_code'] == 0:
        raise RuntimeError('negative consumer case unexpectedly succeeded')

    session.write('consumer_report.json', {
        'kind': 'java-rdd-local',
        'source_jar': next((j for j in own_jars if 'spark-core_' in j), own_jars[0]),
        'install_jars': len(own_jars),
        'positive_log': str(run_log.relative_to(session.output)),
        'negative_tail': (session.output / session.commands[-1]['log']).read_text(errors='replace')[-2000:],
    })

    session.finish({
        'profile': 'core',
        'module': 'core',
        'reactor_dependencies': True,
        'official_suite': SUITE,
        'installed_jars': len(own_jars),
        'consumer': 'java-rdd-local',
    })
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='main.py', description='BUILDv1-E02 Spark core build/test/consumer harness')
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
