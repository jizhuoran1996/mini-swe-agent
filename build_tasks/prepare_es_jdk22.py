"""Provide a real verified Java22 toolchain for Elasticsearch's multi-release JAR."""
import fcntl
import hashlib
import json
import os
import subprocess
import requests
from prepare_sources import ROOT,download,sha


def prepare() -> None:
    runtime=ROOT/'runtime'
    url='https://api.adoptium.net/v3/assets/latest/22/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse'
    response=requests.get(url,timeout=60);response.raise_for_status();assets=response.json()
    assert len(assets)==1 and assets[0]['version']['major']==22
    package=assets[0]['binary']['package'];name=package['name'];archive=runtime/name
    if not archive.exists():download(package['link'],archive)
    assert sha(archive)==package['checksum']
    (runtime/'es-jdk22.official_metadata.json').write_text(json.dumps(assets,indent=2)+'\n')
    record={'url':package['link'],'filename':name,'sha256':package['checksum'],'official_metadata_url':url,'official_metadata_sha256':hashlib.sha256(response.content).hexdigest(),'version':assets[0]['version']['semver'],'role':'genuine Java22 bootstrap for required multi-release source compilation; no Elasticsearch target binary'}
    (runtime/'es-jdk22.lock.json').write_text(json.dumps(record,indent=2)+'\n')
    (runtime/'Dockerfile.es-jdk22').write_text('FROM sbench-build-runtime:v21\nUSER root\nCOPY '+name+' /tmp/java22.tar.gz\nRUN mkdir -p /usr/lib/jvm/temurin-22-jdk && tar -xzf /tmp/java22.tar.gz --strip-components=1 -C /usr/lib/jvm/temurin-22-jdk && rm /tmp/java22.tar.gz\n')
    with (ROOT/'preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with (ROOT/'runs/runtime_es_jdk22.log').open('w') as log:
            subprocess.run(['docker','build','--memory=2g','--memory-swap=2g','--cpu-period=100000','--cpu-quota=200000','--label','sbench.build.runtime=true','-t','sbench-build-runtime:es-jdk22','-f',str(runtime/'Dockerfile.es-jdk22'),str(runtime)],env={**os.environ,'DOCKER_BUILDKIT':'0'},stdout=log,stderr=subprocess.STDOUT,timeout=600,check=True)
    path=runtime/'policy.json';policy=json.loads(path.read_text());policy['task_image_overrides']['BUILDv1-E05']='sbench-build-runtime:es-jdk22';path.write_text(json.dumps(policy,indent=2)+'\n')
    path=ROOT/'tasks/BUILDv1-E05/input/manifest.json';manifest=json.loads(path.read_text());manifest['java22_bootstrap']=record;path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('GENUINE_ES_JAVA22_BOOTSTRAP_READY',record['sha256'],flush=True)


if __name__=='__main__':
    prepare()
