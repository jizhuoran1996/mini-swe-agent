#!/usr/bin/env python3
"""BUILDv1-E03 (core profile).

Build and test Apache Flink's flink-core reactor (-pl flink-core -am), install the
produced JARs under an output install root, and independently consume the freshly
built artifacts from outside the source tree with a positive + negative serialization
program. Offline: all work uses explicit argv lists and the trusted buildkit Session.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import buildkit

MODULE = 'flink-core'
BUILD_GOALS = ['-pl', MODULE, '-am', 'clean', 'package', '-DskipTests', '-Djdk17', '-Pjava17-target']
TEST_GOALS = ['-pl', MODULE, '-am', 'test', '-Djdk17', '-Pjava17-target']

# Consumed only from the install root; uses flink-core's own serialization stack.
CONSUMER_SRC = '''import java.nio.charset.StandardCharsets;
import org.apache.flink.core.memory.DataInputDeserializer;
import org.apache.flink.core.memory.DataOutputSerializer;

public class FlinkCoreSerializationConsumer {
    private static int checks = 0;

    public static void main(String[] args) throws Exception {
        DataOutputSerializer out = new DataOutputSerializer(64);
        out.writeInt(42);
        out.writeLong(123456789L);
        byte[] payload = "flink-core".getBytes(StandardCharsets.UTF_8);
        out.writeInt(payload.length);
        out.write(payload);
        byte[] bytes = out.getCopyOfBuffer();

        DataInputDeserializer in = new DataInputDeserializer(bytes);
        check(in.readInt() == 42, "int roundtrip");
        check(in.readLong() == 123456789L, "long roundtrip");
        int n = in.readInt();
        byte[] buf = new byte[n];
        in.readFully(buf);
        check("flink-core".equals(new String(buf, StandardCharsets.UTF_8)), "bytes roundtrip");

        boolean rejected = false;
        try {
            DataInputDeserializer bad = new DataInputDeserializer(new byte[] {1, 2, 3});
            bad.readLong();
        } catch (Exception e) {
            rejected = true;
        }
        check(rejected, "negative truncated read rejected");

        System.out.println("FlinkCoreSerializationConsumer OK checks=" + checks);
    }

    private static void check(boolean ok, String name) {
        checks++;
        if (!ok) {
            System.err.println("FAIL: " + name);
            System.exit(1);
        }
    }
}
'''

REQUIRED_SOURCE_ENTRIES = ['mvnw', '.mvn/wrapper/maven-wrapper.properties', 'pom.xml', 'flink-core/pom.xml']
REQUIRED_MAVEN_PLUGINS = [
    'org/apache/maven/plugins/maven-surefire-plugin',
    'org/apache/maven/plugins/maven-compiler-plugin',
    'org/apache/maven/plugins/maven-jar-plugin',
    'org/apache/maven/plugins/maven-resources-plugin',
]


def maven_repo():
    for key in ('MAVEN_REPO', 'MAVEN_LOCAL_REPO', 'M2_REPO'):
        value = os.environ.get(key)
        if value:
            return Path(value)
    settings = Path.home() / '.m2' / 'settings.xml'
    if settings.is_file():
        match = re.search(r'<localRepository>\s*([^<]+?)\s*</localRepository>',
                          settings.read_text(errors='replace'))
        if match:
            return Path(match.group(1))
    return Path.home() / '.m2' / 'repository'


def java_tool(name):
    found = shutil.which(name)
    if found:
        return found
    java_home = os.environ.get('JAVA_HOME')
    if java_home and (Path(java_home) / 'bin' / name).is_file():
        return str(Path(java_home) / 'bin' / name)
    return None


def check_environment(input_dir):
    input_dir = Path(input_dir).resolve()
    missing, info = [], {}
    manifest = None
    manifest_path = input_dir / 'manifest.json'
    if not manifest_path.is_file():
        missing.append('missing manifest: %s' % manifest_path)
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception as exc:
            missing.append('unreadable manifest: %s' % exc)
    if manifest:
        info['task_id'] = manifest.get('task_id')
        info['profile'] = manifest.get('profile')
        source = manifest.get('source', {})
        archive = input_dir / source.get('filename', 'source.tar.gz')
        info['archive'] = str(archive)
        if not archive.is_file():
            missing.append('missing source archive: %s' % archive)
        else:
            try:
                actual = buildkit.digest(archive)
                info['sha256'] = actual
                if source.get('sha256') and actual != source['sha256']:
                    missing.append('source sha256 mismatch: %s != %s' % (actual, source['sha256']))
            except Exception as exc:
                missing.append('unreadable source archive: %s' % exc)
            names = []
            try:
                with tarfile.open(archive) as tar:
                    names = tar.getnames()
            except Exception as exc:
                missing.append('invalid source tar: %s' % exc)
            for required in REQUIRED_SOURCE_ENTRIES:
                if not any(n == required or n.endswith('/' + required) for n in names):
                    missing.append('source entry missing: %s' % required)
            if names:
                info['top_level'] = sorted({n.split('/')[0] for n in names if '/' in n})[:6]
    java = java_tool('java')
    if not java:
        missing.append('tool missing: java (JDK 17+)')
    else:
        info['java'] = java
        try:
            proc = subprocess.run([java, '-version'], capture_output=True, text=True, timeout=120)
            lines = (proc.stderr or proc.stdout).strip().splitlines()
            version = lines[0] if lines else 'unknown'
            info['java_version'] = version
            match = re.search(r'version "(\d+)', version)
            if not match or int(match.group(1)) < 17:
                missing.append('java version must be >= 17: %s' % version)
        except Exception as exc:
            missing.append('cannot run java: %s' % exc)
    if not java_tool('javac'):
        missing.append('tool missing: javac (JDK 17+)')
    repo = maven_repo()
    info['maven_repo'] = str(repo)
    if not repo.is_dir():
        missing.append('offline maven repository absent: %s' % repo)
    elif not any(repo.iterdir()):
        missing.append('offline maven repository empty: %s' % repo)
    else:
        info['maven_repo_entries'] = len(list(repo.iterdir()))
        for artifact in REQUIRED_MAVEN_PLUGINS:
            if not (repo / artifact).is_dir():
                missing.append('maven artifact missing: %s' % artifact)
        if not (repo / 'org' / 'apache' / 'flink').is_dir():
            missing.append('maven artifacts missing: org/apache/flink (flink-shaded & deps)')
    return missing, info


def cmd_doctor(args):
    missing, info = check_environment(args.input)
    report = {'ready': not missing, 'missing': missing, 'info': info}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 78 if missing else 0


def cmd_run(args):
    missing, info = check_environment(args.input)
    if missing:
        print(json.dumps({'ready': False, 'missing': missing, 'info': info},
                         indent=2, sort_keys=True))
        return 78
    session = buildkit.Session(args.input, args.output, args.jobs)
    session.prepare()
    src = session.src
    mvnw = src / 'mvnw'
    mvnw.chmod(0o755)
    repo = maven_repo()
    env = os.environ.copy()
    env.setdefault('MAVEN_OPTS', '-Xmx3g -Dfile.encoding=UTF-8')
    repo_arg = ['-Dmaven.repo.local=%s' % repo] if repo.is_dir() else []
    session.run([str(mvnw), '-o', *repo_arg, *BUILD_GOALS], cwd=src, phase='build',
                name='flink_core_package', env=env, timeout=10800)
    session.test('flink_core_official_tests',
                 [str(mvnw), '-o', *repo_arg, *TEST_GOALS], cwd=src, env=env, timeout=10800)

    jars = []
    for candidate in sorted(src.rglob('*.jar')):
        if candidate.parent.name != 'target':
            continue
        name = candidate.name
        if 'sources' in name or 'javadoc' in name or '-tests.jar' in name:
            continue
        jars.append(candidate)
    if not any(re.match(r'flink-core-\d', jar.name) for jar in jars):
        raise RuntimeError('flink-core jar not produced by the build')
    lib = session.install / 'lib'
    lib.mkdir(parents=True, exist_ok=True)
    for jar in jars:
        shutil.copy2(jar, lib / jar.name)
    session.write('modules.json', {
        'module': MODULE,
        'build_goals': BUILD_GOALS,
        'test_goals': TEST_GOALS,
        'jars': sorted(p.name for p in lib.glob('*.jar')),
    })

    consumer_dir = session.consumer
    consumer_dir.mkdir(parents=True, exist_ok=True)
    java_file = consumer_dir / 'FlinkCoreSerializationConsumer.java'
    java_file.write_text(CONSUMER_SRC)
    classes = consumer_dir / 'classes'
    classes.mkdir(parents=True, exist_ok=True)
    classpath = os.pathsep.join(str(p) for p in sorted(lib.glob('*.jar')))
    javac = java_tool('javac')
    java = java_tool('java')
    session.run([javac, '-cp', classpath, '-d', str(classes), str(java_file)],
                cwd=consumer_dir, phase='consumer', name='consumer_compile', timeout=900)
    session.run([java, '-cp', classpath + os.pathsep + str(classes),
                 'FlinkCoreSerializationConsumer'],
                cwd=consumer_dir, phase='consumer', name='consumer_run', timeout=900)

    session.finish(features={
        'module': MODULE,
        'build_goals': BUILD_GOALS,
        'test_goals': TEST_GOALS,
        'install_jars': sorted(p.name for p in lib.glob('*.jar')),
        'consumer': 'FlinkCoreSerializationConsumer (positive + negative serialization roundtrip)',
    })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='main.py', description=__doc__)
    sub = parser.add_subparsers(dest='command')
    run_p = sub.add_parser('run', help='build, test, install and consume flink-core')
    run_p.add_argument('--input', required=True)
    run_p.add_argument('--output', required=True)
    run_p.add_argument('--jobs', type=int, default=4)
    doc_p = sub.add_parser('doctor', help='report missing source/tool/dependency items')
    doc_p.add_argument('--input', required=True)
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        return cmd_doctor(args)
    if args.command == 'run':
        args.jobs = min(max(int(args.jobs), 1), 4)
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
