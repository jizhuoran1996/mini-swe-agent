#!/usr/bin/env python3
"""BUILDv1-E05 (frozen CORE profile) task driver.

CORE scope (deliberately narrower than the reference instance):
  * build the genuine :server product JAR of Elasticsearch v8.17.6 as a
    RELEASE artifact (not a snapshot) so its manifest carries the strict
    Implementation-Version=8.17.6;
  * run the frozen query-package unit test selection
    (org.elasticsearch.index.query.MatchQueryBuilderTests);
  * install the produced JAR PLUS its genuine dependency closure into an
    out-of-tree INSTALL_ROOT and consume it from independent, JDK-only Java
    verifiers that compile and run using ONLY the delivered files (library
    consumers, NOT a running service).

Release metadata (source-backed, unchanged upstream mechanism):
  build-tools-internal/src/main/java/org/elasticsearch/gradle/internal/info/
  GlobalBuildInfoPlugin.java reads Util.getBooleanProperty("build.snapshot",
  true), so an unmodified invocation defaults to snapshot metadata and yields
  elasticsearch-<version>-SNAPSHOT.jar. The upstream supported way to obtain
  the release artifact is -Dbuild.snapshot=false, exactly as
  build-tools-internal/src/main/java/org/elasticsearch/gradle/internal/
  BwcSetupExtension.java already uses. Therefore -Dbuild.snapshot=false is
  passed on EVERY Gradle invocation and nothing about the produced JAR (name,
  manifest, contents) is renamed, rewritten, stripped or forged.

Genuine product location (source-backed):
  build-tools-internal/src/main/java/org/elasticsearch/gradle/internal/
  ElasticsearchJavaPlugin.java declares
      jarTask.getDestinationDirectory().set(new File(project.getBuildDir(),
          "distributions"));
  so real :server output is server/build/distributions/elasticsearch-<version>.jar
  (base.archivesName = 'elasticsearch' in server/build.gradle). Every other
  project jar configured by that plugin also lands under its own
  build/distributions.

Deployment / SDK closure (this fix):
  The delivered install.tar.gz must be consumable in a fresh container that has
  no extracted source and no Gradle cache. Every dependency JAR a Java consumer
  needs is copied byte for byte, with its original filename, into
  INSTALL_ROOT/lib. Byte-identical entries are deduplicated; a filename
  collision with differing content fails loudly; a classpath entry that cannot
  be resolved to a real JAR (including a class directory that has no project JAR
  counterpart) fails loudly. No dummy or synthesised JAR is ever created and no
  upstream code or product bytes are modified.

Toolchain handling (Gradle 8.13): the driver merges
GRADLE_USER_HOME/gradle.properties with the local JDK paths and
auto-download=false / auto-detect=true, and also passes the matching -P entries
on every Gradle invocation so the setting reaches the included builds.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

from buildkit import Session, digest


RELEASE_GRADLE_FLAGS = ('-Dbuild.snapshot=false',)
EXPECTED_IMPLEMENTATION_VERSION = '8.17.6'

_JDK_BASES = ('/usr/lib/jvm', '/usr/lib64/jvm', '/workspace/cache/gradle/jdks')

_VERSION_PROPERTY_FILES = (
    ('build-tools-internal', 'src', 'main', 'resources', 'version.properties'),
    ('build-tools-internal', 'version.properties'),
    ('build-tools', 'src', 'main', 'resources', 'version.properties'),
    ('build-tools', 'version.properties'),
)

_SERVER_JAR_DIRS = ('distributions', 'libs')


def _jdk_major(jdk_root):
    javac = Path(jdk_root) / 'bin' / 'javac'
    if not javac.is_file():
        return None
    try:
        proc = subprocess.run([str(javac), '-version'], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    text = proc.stdout + proc.stderr
    index = text.find('javac')
    if index < 0:
        return None
    digits = ''
    for ch in text[index + 5:].lstrip():
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else None


def _detect_jdks():
    found = {}
    seen = set()
    for base in _JDK_BASES:
        root = Path(base)
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir())
        except OSError:
            continue
        for child in children:
            resolved = str(child.resolve())
            if resolved in seen:
                continue
            major = _jdk_major(child)
            if major:
                seen.add(resolved)
                found.setdefault(major, []).append(resolved)
    return found


def _gradle_home():
    if os.environ.get('GRADLE_USER_HOME'):
        return Path(os.environ['GRADLE_USER_HOME'])
    return Path(os.environ.get('HOME', '/tmp')) / '.gradle'


def diagnose(input_dir):
    missing = []
    input_dir = Path(input_dir)
    manifest_path = input_dir / 'manifest.json'
    manifest = None
    if not manifest_path.is_file():
        missing.append({'item': 'manifest.json', 'kind': 'source',
                        'detail': str(manifest_path)})
    else:
        manifest = json.loads(manifest_path.read_text())
    archive = None
    if manifest:
        archive = input_dir / manifest['source']['filename']
        if not archive.is_file():
            missing.append({'item': manifest['source']['filename'],
                            'kind': 'source', 'detail': str(archive)})
        elif digest(archive) != manifest['source']['sha256']:
            missing.append({'item': manifest['source']['filename'],
                            'kind': 'source', 'detail': 'sha256 mismatch'})
    for tool in ('java', 'javac', 'tar'):
        if shutil.which(tool) is None:
            missing.append({'item': tool, 'kind': 'tool', 'detail': 'not on PATH'})
    jdks = _detect_jdks()
    if not any(major >= 21 for major in jdks):
        missing.append({'item': 'jdk-21 (build toolchain)', 'kind': 'tool',
                        'detail': 'no JDK >=21 under ' + str(_JDK_BASES)})
    if 17 not in jdks:
        missing.append({'item': 'jdk-17 (libs toolchain)', 'kind': 'tool',
                        'detail': 'no JDK 17 under ' + str(_JDK_BASES)})
    if archive is not None and archive.is_file():
        try:
            with tarfile.open(archive) as handle:
                names = set(handle.getnames())
            roots = {n.split('/', 1)[0] for n in names}
            root = next(iter(roots)) if roots else ''
            for rel in ('gradlew', 'gradle/wrapper/gradle-wrapper.jar',
                        'gradle/wrapper/gradle-wrapper.properties',
                        'server/build.gradle',
                        'build-tools-internal/version.properties',
                        'build-tools-internal/src/main/java/org/elasticsearch/'
                        'gradle/internal/ElasticsearchJavaPlugin.java',
                        'build-tools-internal/src/main/java/org/elasticsearch/'
                        'gradle/internal/info/GlobalBuildInfoPlugin.java'):
                if root + '/' + rel not in names:
                    missing.append({'item': rel, 'kind': 'source',
                                    'detail': 'absent from source archive'})
        except tarfile.TarError as exc:
            missing.append({'item': 'source archive', 'kind': 'source',
                            'detail': 'unreadable: ' + str(exc)})
    wrapper = _gradle_home() / 'wrapper' / 'dists'
    if not wrapper.is_dir() or not any(wrapper.iterdir()):
        missing.append({'item': 'gradle-wrapper-distribution', 'kind': 'dependency',
                        'detail': 'no Gradle distribution under ' + str(wrapper)})
    caches = _gradle_home() / 'caches' / 'modules-2'
    if not caches.is_dir():
        missing.append({'item': 'gradle-dependency-cache', 'kind': 'dependency',
                        'detail': 'no offline dependency cache under ' + str(caches)})
    return missing


_MANAGED_PROPERTIES = ('org.gradle.java.installations.paths',
                       'org.gradle.java.installations.auto-download',
                       'org.gradle.java.installations.auto-detect')


def _write_user_gradle_properties(paths):
    gh = _gradle_home()
    gh.mkdir(parents=True, exist_ok=True)
    props_path = gh / 'gradle.properties'
    managed = {
        'org.gradle.java.installations.paths': ','.join(paths),
        'org.gradle.java.installations.auto-download': 'false',
        'org.gradle.java.installations.auto-detect': 'true',
    }
    kept = []
    if props_path.is_file():
        try:
            existing = props_path.read_text().splitlines()
        except OSError:
            existing = []
        for line in existing:
            key = line.split('=', 1)[0].strip() if '=' in line else None
            if key in _MANAGED_PROPERTIES:
                continue
            kept.append(line)
    out = kept + [key + '=' + value for key, value in managed.items()]
    props_path.write_text('\n'.join(out).rstrip('\n') + '\n')
    return props_path


def _build_environment():
    jdks = _detect_jdks()
    flat_paths = sorted({p for paths in jdks.values() for p in paths})
    _write_user_gradle_properties(flat_paths)
    build_jdk = None
    for major in sorted(m for m in jdks if m >= 21):
        build_jdk = jdks[major][0]
        break
    if build_jdk is None and os.environ.get('JAVA_HOME'):
        build_jdk = os.environ['JAVA_HOME']
    if build_jdk is None:
        java = shutil.which('java')
        if java:
            build_jdk = str(Path(java).resolve().parent.parent)
    env = {'GRADLE_USER_HOME': str(_gradle_home()),
           'GRADLE_OPTS': '-Dorg.gradle.jvmargs=-Xmx4g'}
    if build_jdk:
        env['JAVA_HOME'] = build_jdk
    return env, flat_paths, build_jdk


def _gradle_extra_flags(flat_paths):
    if not flat_paths:
        return []
    joined = ','.join(flat_paths)
    return ['-Porg.gradle.java.installations.paths=' + joined,
            '-Porg.gradle.java.installations.auto-download=false',
            '-Porg.gradle.java.installations.auto-detect=true']


def _strip_snapshot(raw):
    raw = raw.strip().strip('"').strip()
    if raw.endswith('-SNAPSHOT'):
        return raw[:-len('-SNAPSHOT')]
    return raw


def _declared_version(src):
    for parts in _VERSION_PROPERTY_FILES:
        path = src.joinpath(*parts)
        if not path.is_file():
            continue
        for line in path.read_text(errors='replace').splitlines():
            stripped = line.strip()
            if '=' in stripped and stripped.split('=', 1)[0].strip() == 'version':
                candidate = _strip_snapshot(stripped.split('=', 1)[1])
                if candidate:
                    return candidate
    toml = src / 'gradle' / 'build.versions.toml'
    if toml.is_file():
        for line in toml.read_text(errors='replace').splitlines():
            stripped = line.strip()
            if '=' in stripped and stripped.split('=', 1)[0].strip() == 'elasticsearch':
                return _strip_snapshot(stripped.split('=', 1)[1])
    return None


def _server_jar_dirs(src):
    base = src / 'server' / 'build'
    return [base / name for name in _SERVER_JAR_DIRS]


def _is_genuine_server_jar(path):
    if not path.is_file():
        return False
    if path.name.endswith(('-sources.jar', '-javadoc.jar', '-tests.jar')):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError):
        return False
    return ('org/elasticsearch/Version.class' in names
            and 'org/elasticsearch/index/query/MatchQueryBuilder.class' in names)


def _find_server_jar(src, expected_version, reported=None):
    observed = []
    scanned = []
    for directory in _server_jar_dirs(src):
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.glob('*.jar')):
            observed.append(str(candidate.relative_to(src)))
            scanned.append(candidate)
    ordered = []

    def add(candidate):
        if candidate is not None and candidate not in ordered:
            ordered.append(candidate)

    if expected_version:
        for directory in _server_jar_dirs(src):
            add(directory / ('elasticsearch-' + expected_version + '.jar'))
    if reported:
        add(Path(reported))
    if expected_version:
        for directory in _server_jar_dirs(src):
            add(directory / ('elasticsearch-' + expected_version + '-SNAPSHOT.jar'))
    for candidate in scanned:
        add(candidate)
    for candidate in ordered:
        if _is_genuine_server_jar(candidate):
            return candidate, observed
    return None, observed


def _resolve_jar_entry(entry, src):
    path = Path(entry)
    if path.is_file():
        return path
    if not path.is_dir():
        return None
    try:
        rel = path.relative_to(src)
    except ValueError:
        return None
    parts = list(rel.parts)
    if 'build' not in parts:
        return None
    index = parts.index('build')
    project_dir = src.joinpath(*parts[:index]) if index else src
    for sub in ('distributions', 'libs'):
        directory = project_dir / 'build' / sub
        if not directory.is_dir():
            continue
        for jar in sorted(directory.glob('*.jar')):
            name = jar.name
            if name.endswith(('-sources.jar', '-javadoc.jar', '-tests.jar')):
                continue
            return jar
    return None


def _stage_closure(entries, src, install, server_jar):
    server_hash = digest(server_jar)
    lib_dir = install / 'lib'
    lib_dir.mkdir(parents=True, exist_ok=True)
    unresolved = []
    chosen = {}
    for entry in entries:
        jar = _resolve_jar_entry(entry, src)
        if jar is None:
            unresolved.append(entry)
            continue
        try:
            content_hash = digest(jar)
        except OSError:
            unresolved.append(str(jar))
            continue
        if content_hash == server_hash:
            continue
        name = jar.name
        if name in chosen:
            if chosen[name][1] != content_hash:
                raise RuntimeError(
                    'delivered-JAR filename collision with differing content: ' + name)
            continue
        chosen[name] = (jar, content_hash)
    records = []
    for name in sorted(chosen):
        jar, content_hash = chosen[name]
        target = lib_dir / name
        shutil.copy2(jar, target)
        if digest(target) != content_hash:
            raise RuntimeError('staged JAR bytes changed: ' + str(target))
        records.append({'name': name, 'source_path': str(jar),
                        'bytes': target.stat().st_size, 'sha256': content_hash})
    return records, unresolved, chosen


def execute(args):
    missing = diagnose(args.input)
    hard = [m for m in missing if m['kind'] == 'source']
    if hard:
        print(json.dumps({'status': 'missing-input', 'items': hard}, indent=2))
        return 78

    session = Session(args.input, args.output, args.jobs)
    session.prepare()

    solution_dir = Path(__file__).resolve().parent
    env, flat_paths, build_jdk = _build_environment()
    extra = _gradle_extra_flags(flat_paths)
    gradlew = str(session.src / 'gradlew')
    workers = max(1, min(int(args.jobs), 4))

    jdk_bin = Path(build_jdk) / 'bin' if build_jdk else Path('/usr/bin')
    javac = str(jdk_bin / 'javac') if (jdk_bin / 'javac').is_file() else 'javac'
    java_bin = str(jdk_bin / 'java') if (jdk_bin / 'java').is_file() else 'java'

    consumer_dir = session.consumer / 'verify'
    consumer_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(solution_dir / 'java' / 'EsArtifactVerifier.java',
                consumer_dir / 'EsArtifactVerifier.java')
    shutil.copy(solution_dir / 'java' / 'InstalledClosureVerifier.java',
                consumer_dir / 'InstalledClosureVerifier.java')
    init_script = consumer_dir / 'consumer-classpath.init.gradle'
    shutil.copy(solution_dir / 'gradle' / 'consumer-classpath.init.gradle',
                init_script)
    classpath_file = consumer_dir / 'server-classpath.txt'
    jar_report_file = consumer_dir / 'server-jar-path.txt'

    # -Dbuild.snapshot=false is the upstream-supported release switch (see
    # BwcSetupExtension.java). It is applied on EVERY Gradle invocation so the
    # manifest carries the strict release Implementation-Version=8.17.6.
    common = ['--offline', '--no-daemon', '--no-build-cache', '--console=plain',
              *RELEASE_GRADLE_FLAGS]

    # 0) diagnostic: show the JDK toolchains Gradle can actually see (non-fatal).
    session.run([gradlew, '--offline', '--no-daemon', '--console=plain', '-q',
                 *RELEASE_GRADLE_FLAGS, 'javaToolchains'] + extra,
                cwd=session.src, phase='diagnostic', name='java_toolchains',
                env=env, timeout=900, check=False)

    # 1) build the :server release product JAR only (CORE profile, not localDistro).
    session.run([gradlew] + common + ['-Dorg.gradle.workers.max=' + str(workers)]
                + extra + [':server:jar'],
                cwd=session.src, phase='build', name='gradle_server_jar',
                env=env, timeout=7200)

    # 2) authoritative introspection: genuine Jar archiveFile + genuine consumer
    #    classpath, both resolved offline by Gradle (no project source modified).
    session.run([gradlew] + common + extra + ['-I', str(init_script),
                 '-Pes.consumer.cp.out=' + str(classpath_file),
                 '-Pes.server.jar.out=' + str(jar_report_file),
                 ':server:esDumpConsumerClasspath', ':server:esReportServerJar'],
                cwd=session.src, phase='build', name='gradle_artifact_introspection',
                env=env, timeout=1800)

    reported_jar = None
    if jar_report_file.is_file():
        text = jar_report_file.read_text().strip()
        if text and text.lower() != '<unresolved>':
            reported_jar = text.splitlines()[0].strip()

    expected_version = _declared_version(session.src)
    server_jar, observed = _find_server_jar(session.src, expected_version,
                                            reported=reported_jar)
    if server_jar is None:
        raise RuntimeError(
            'genuine :server product JAR not found (declared version=' + repr(expected_version)
            + '; build.snapshot=false; gradle-reported=' + repr(reported_jar)
            + '; jars present in server/build/{' + ','.join(_SERVER_JAR_DIRS) + '}='
            + repr(observed) + ')')

    if not classpath_file.is_file() or not classpath_file.read_text().strip():
        raise RuntimeError('failed to resolve the :server dependency closure for the consumer')
    closure_entries = [p for p in classpath_file.read_text().strip().split(os.pathsep) if p]

    # 3) frozen query-package unit test selection (nonempty by construction).
    session.test('MatchQueryBuilderTests',
                 [gradlew] + common + ['-Dorg.gradle.workers.max=' + str(min(2, workers))]
                 + extra + [':server:test', '--tests',
                            'org.elasticsearch.index.query.MatchQueryBuilderTests',
                            '-Dtests.seed=DEADBEEF'],
                 cwd=session.src, env=env, timeout=3600)

    # 4) install the genuine product JAR into the out-of-tree INSTALL_ROOT,
    #    keeping its true upstream release file name elasticsearch-8.17.6.jar.
    session.install.mkdir(parents=True, exist_ok=True)
    installed = session.install / server_jar.name
    shutil.copy(server_jar, installed)
    (session.install / 'INSTALL_SCOPE.txt').write_text(
        'core-scope: genuine Elasticsearch :server product JAR (' + server_jar.name + ') '
        'built with -Dbuild.snapshot=false, plus its genuine dependency closure '
        'under lib/ and the frozen org.elasticsearch.index.query '
        'MatchQueryBuilderTests selection. This is a library artifact, not a '
        'running Elasticsearch service.\n')
    (session.install / 'MODULE_SCOPE.txt').write_text(
        'core-scope: :server JAR + org.elasticsearch.index.query unit tests only\n')

    # 5) stage the genuine dependency closure into INSTALL_ROOT/lib so the
    #    delivery is consumable without the source tree or the Gradle cache.
    records, unresolved, chosen = _stage_closure(
        closure_entries, session.src, session.install, installed)
    if unresolved:
        raise RuntimeError('required consumer classpath entries could not be '
                           'resolved to real JAR files: ' + repr(unresolved))
    if not chosen:
        raise RuntimeError('no dependency JARs were staged into INSTALL_ROOT/lib')

    rel_lines = [installed.name] + ['lib/' + name for name in sorted(chosen)]
    (session.install / 'consumer-classpath.txt').write_text(
        '\n'.join(rel_lines) + '\n')
    abs_paths = [str(installed)] + [str(session.install / 'lib' / name)
                                    for name in sorted(chosen)]
    installed_cp_file = consumer_dir / 'installed-classpath.txt'
    installed_cp_file.write_text(os.pathsep.join(abs_paths) + '\n')
    (session.install / 'STAGED_JARS.json').write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + '\n')

    # 6) independent consumer: compile outside the source tree and verify the
    #    installed JAR (positive case) using ONLY the delivered closure.
    consumer_env = dict(env)
    session.run([javac, '-d', str(consumer_dir), str(consumer_dir / 'EsArtifactVerifier.java')],
                cwd=consumer_dir, phase='consumer', name='javac_verifier',
                env=consumer_env, timeout=300)
    session.run([java_bin, '-cp', str(consumer_dir), 'EsArtifactVerifier',
                 str(installed), str(installed_cp_file)],
                cwd=consumer_dir, phase='consumer', name='java_verifier_positive',
                env=consumer_env, timeout=300)

    # 7) negative case A: a non-JAR file must be rejected.
    bogus = consumer_dir / 'not-a-jar.bin'
    bogus.write_bytes(b'this is not a jar file')
    session.run([java_bin, '-cp', str(consumer_dir), 'EsArtifactVerifier',
                 str(bogus), str(installed_cp_file)],
                cwd=consumer_dir, phase='consumer', name='java_verifier_negative_notjar',
                env=consumer_env, timeout=300, check=False)
    negative_notjar = session.commands[-1]['exit_code']
    if negative_notjar == 0:
        raise RuntimeError('consumer negative case (non-JAR) unexpectedly succeeded')

    # 8) negative case B: a structurally valid JAR that lacks the required
    #    query-package classes must also be rejected.
    hollow = consumer_dir / 'hollow.jar'
    with zipfile.ZipFile(hollow, 'w') as archive:
        archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\n')
        archive.writestr('placeholder.txt', 'not the server artifact\n')
    session.run([java_bin, '-cp', str(consumer_dir), 'EsArtifactVerifier',
                 str(hollow), str(installed_cp_file)],
                cwd=consumer_dir, phase='consumer', name='java_verifier_negative_hollow',
                env=consumer_env, timeout=300, check=False)
    negative_hollow = session.commands[-1]['exit_code']
    if negative_hollow == 0:
        raise RuntimeError('consumer negative case (hollow JAR) unexpectedly succeeded')

    # 9) installed-closure verifier: compile and run against the DELIVERED files
    #    only (no source tree, no Gradle cache), exercising the real query APIs.
    session.run([javac, '-cp', os.pathsep.join(abs_paths), '-d', str(consumer_dir),
                 str(consumer_dir / 'InstalledClosureVerifier.java')],
                cwd=consumer_dir, phase='consumer', name='javac_installed_closure',
                env=consumer_env, timeout=300)
    session.run([java_bin, '-cp', str(consumer_dir) + os.pathsep + os.pathsep.join(abs_paths),
                 'InstalledClosureVerifier', str(session.install)],
                cwd=consumer_dir, phase='consumer', name='java_installed_closure_positive',
                env=consumer_env, timeout=300)

    manifest = json.loads((session.input / 'manifest.json').read_text())
    session.write('verify.json', {
        'server_jar': server_jar.name,
        'server_jar_source_path': str(server_jar.relative_to(session.src)),
        'server_jar_reported_by_gradle': reported_jar,
        'declared_version': expected_version,
        'expected_implementation_version': EXPECTED_IMPLEMENTATION_VERSION,
        'build_snapshot': False,
        'install_path': str(installed),
        'sha256': digest(installed),
        'scope': 'core release (:server JAR + query unit tests)',
        'release_ref': manifest['source'].get('release_ref'),
        'jdks_seen': {str(k): v for k, v in _detect_jdks().items()},
        'closure_entries_resolved': len(closure_entries),
        'closure_jars_staged': len(chosen),
        'staged_jars': records,
        'consumer_classpath_relocatable': str(session.install / 'consumer-classpath.txt'),
        'negative_case_exit_codes': {'not_a_jar': negative_notjar,
                                     'hollow_jar': negative_hollow},
        'not_a_full_service': True,
    })
    session.finish(features={'scope': 'core',
                             'target': ':server:jar',
                             'release_build': True,
                             'build_snapshot': False,
                             'server_artifact': server_jar.name,
                             'server_artifact_dir': 'server/build/distributions',
                             'implementation_version': EXPECTED_IMPLEMENTATION_VERSION,
                             'tests': ['org.elasticsearch.index.query.MatchQueryBuilderTests'],
                             'staged_dependency_jars': len(chosen),
                             'consumers': ['solution/java/EsArtifactVerifier.java',
                                           'solution/java/InstalledClosureVerifier.java'],
                             'negative_consumers': ['not-a-jar.bin', 'hollow.jar'],
                             'full_distribution_built': False})
    print('BUILDv1-E05 core: release :server JAR built, tested, installed with '
          'closure and verified ->', session.output)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='main.py',
        description='BUILDv1-E05 CORE: build the genuine Elasticsearch :server release JAR '
                    '(-Dbuild.snapshot=false), run the frozen query unit tests, install '
                    'the JAR plus its dependency closure and independently verify.')
    subs = parser.add_subparsers(dest='command')
    doc = subs.add_parser('doctor',
                          help='report exact missing source/tool/dependency items (78 if missing)')
    doc.add_argument('--input', required=True,
                     help='read-only input dir containing manifest.json + source archive')
    run = subs.add_parser('run', help='build, test, install and independently verify')
    run.add_argument('--input', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)

    if args.command == 'doctor':
        missing = diagnose(args.input)
        print(json.dumps({'status': 'missing' if missing else 'ready',
                          'profile': 'core', 'items': missing},
                         ensure_ascii=False, indent=2))
        return 78 if missing else 0
    if args.command == 'run':
        return execute(args)
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
