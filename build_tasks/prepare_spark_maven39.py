"""Freeze the genuine Maven3.9.6 bootstrap required by Spark's enforcer."""
import fcntl
import hashlib
import json
import os
import subprocess
from pathlib import Path
import requests
from prepare_sources import ROOT,download,sha


def prepare() -> None:
    runtime=ROOT/'runtime'
    name='apache-maven-3.9.6-bin.tar.gz'
    url='https://archive.apache.org/dist/maven/maven-3/3.9.6/binaries/'+name
    response=requests.get(url+'.sha512',timeout=60);response.raise_for_status()
    checksum=response.text.strip();assert len(checksum)==128
    archive=runtime/name
    if not archive.exists():download(url,archive)
    assert hashlib.sha512(archive.read_bytes()).hexdigest()==checksum
    (runtime/'spark-maven39.official.sha512.txt').write_text(checksum+'\n')
    record={'url':url,'filename':name,'sha256':sha(archive),'sha512':checksum,
            'official_checksum_url':url+'.sha512','role':'genuine source build bootstrap only; no Spark binaries'}
    (runtime/'spark-maven39.lock.json').write_text(json.dumps(record,indent=2)+'\n')
    (runtime/'Dockerfile.spark-maven39').write_text('FROM sbench-build-runtime:v21\nUSER root\nCOPY '+name+' /tmp/maven39.tar.gz\nRUN mkdir -p /opt/bootstrap/maven39 && tar -xzf /tmp/maven39.tar.gz --strip-components=1 -C /opt/bootstrap/maven39 && rm /tmp/maven39.tar.gz && ln -sf /opt/bootstrap/maven39/bin/mvn /usr/bin/mvn && update-alternatives --set java /usr/lib/jvm/java-17-openjdk-amd64/bin/java && update-alternatives --set javac /usr/lib/jvm/java-17-openjdk-amd64/bin/javac\nENV PATH="/opt/bootstrap/maven39/bin:${PATH}"\n')
    with (ROOT/'preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with (ROOT/'runs/runtime_spark_maven39.log').open('w') as log:
            subprocess.run(['docker','build','--memory=2g','--memory-swap=2g','--cpu-period=100000','--cpu-quota=200000','--label','sbench.build.runtime=true','-t','sbench-build-runtime:spark-maven39','-f',str(runtime/'Dockerfile.spark-maven39'),str(runtime)],env={**os.environ,'DOCKER_BUILDKIT':'0'},stdout=log,stderr=subprocess.STDOUT,timeout=600,check=True)
    path=runtime/'policy.json';policy=json.loads(path.read_text());policy['task_image_overrides']['BUILDv1-E02']='sbench-build-runtime:spark-maven39';path.write_text(json.dumps(policy,indent=2)+'\n')
    path=ROOT/'tasks/BUILDv1-E02/input/manifest.json';manifest=json.loads(path.read_text());manifest['maven_bootstrap']=record;manifest['maven_bootstrap']['version']='3.9.6';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('GENUINE_SPARK_MAVEN39_READY',record['sha256'],flush=True)


if __name__=='__main__':
    prepare()
