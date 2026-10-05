"""Freeze the real Maven wrapper distribution required by the Flink source."""
from input_storage import link_input
import json
import time
from container import ROOT, Sandbox
from prepare_sources import sha
from status import write_json

SCRIPT = r'''
import hashlib,json,os,shutil,tarfile
from pathlib import Path
import buildkit
s=buildkit.Session('/workspace/input','/workspace/output',jobs=2);s.prepare()
wrapper=s.src/'mvnw';wrapper.chmod(0o755)
s.run([str(wrapper),'--version'],cwd=s.src,phase='bootstrap_resolution',
      name='genuine_source_maven_wrapper_version_no_target_build',timeout=600)
jar=s.src/'.mvn/wrapper/maven-wrapper.jar'
properties=(s.src/'.mvn/wrapper/maven-wrapper.properties').read_text()
assert 'apache-maven/3.8.6/apache-maven-3.8.6-bin.zip' in properties
assert 'distributionSha256Sum=ccf20a80e75a17ffc34d47c5c95c98c39d426ca17d670f09cd91e877072a9309' in properties
checksum=buildkit.digest(jar)
assert checksum=='e63a53cfb9c4d291ebe3c2b0edacb7622bbc480326beaa5a0456e412f52f066a'
shutil.copy2(jar,s.output/'maven-wrapper-3.2.0.jar')
with tarfile.open(s.output/'maven-wrapper-dependencies.tar.gz','w:gz',compresslevel=1) as archive:
    archive.add(Path.home()/'.m2/wrapper',arcname='maven_wrapper')
s.write('bootstrap_resolution.json',{'target_compiled':False,'target_outputs_exported':False,
    'wrapper_version':'3.2.0','distribution_version':'3.8.6',
    'distribution_sha256_from_frozen_source':'ccf20a80e75a17ffc34d47c5c95c98c39d426ca17d670f09cd91e877072a9309',
    'wrapper_jar_sha256':checksum,'cache_materialization':'genuine wrapper --version installation; native hydrator restores HOME/.m2/wrapper'})
'''


def prepare() -> None:
    task = ROOT / 'tasks/BUILDv1-E03'
    run = ROOT / 'runs' / ('prepare_flink_wrapper_' + str(time.time_ns()))
    run.mkdir(parents=True)
    script = run / 'resolve.py'; script.write_text(SCRIPT)
    with Sandbox('BUILDv1-E03-prepare', inputs=task / 'input', report_dir=run / 'isolation', preparation=True) as box:
        box.put(script, '/workspace/resolve.py')
        result = box.exec(['python3', 'resolve.py'], timeout=800)
        collected = box.collect(run)
    write_json(run / 'result.json', result)
    assert result['exit_code'] == 0 and collected['collected'], result
    path = task / 'input/manifest.json'; manifest = json.loads(path.read_text())
    archive = run / 'output/maven-wrapper-dependencies.tar.gz'
    target = task / 'input' / archive.name; link_input(target,archive)
    jar = run / 'output/maven-wrapper-3.2.0.jar'
    jar_target = task / 'input' / jar.name; link_input(jar_target,jar)
    manifest['dependency_caches'] += [{'filename': target.name, 'bytes': target.stat().st_size,
        'sha256': sha(target), 'preparation_run': run.name, 'target_outputs_exported': False}]
    manifest.setdefault('dependency_source_overlays', []).append({'filename': jar_target.name,
        'sha256': sha(jar_target), 'bytes': jar_target.stat().st_size,
        'source_relative_destination': '.mvn/wrapper/maven-wrapper.jar',
        'source': 'https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.2.0/maven-wrapper-3.2.0.jar',
        'upstream_validation': 'Exact SHA256 supplied by the frozen source; actual official wrapper bootstrap'})
    manifest['maven_wrapper_bootstrap'] = json.loads((run / 'output/bootstrap_resolution.json').read_text())
    write_json(path, manifest)
    print('GENUINE_FLINK_SOURCE_MAVEN_WRAPPER_READY', flush=True)


if __name__ == '__main__':
    prepare()
