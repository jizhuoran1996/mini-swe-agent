"""Freeze a genuine Node 20 bootstrap for Rollup's unchanged legacy warning tests."""
import hashlib,json,os,subprocess
from pathlib import Path
import requests
from prepare_sources import ROOT,download,sha
runtime=ROOT/'runtime'
name='node-v20.18.3-linux-x64.tar.xz'
base='https://nodejs.org/dist/v20.18.3/'
response=requests.get(base+'SHASUMS256.txt',timeout=60);response.raise_for_status()
checksums=response.text
checksum=next(line.split()[0] for line in checksums.splitlines() if line.split()[-1]==name)
assert len(checksum)==64
archive=runtime/name
if not archive.exists():download(base+name,archive)
assert sha(archive)==checksum
(runtime/'rollup-node20.SHASUMS256.txt').write_text(checksums)
(runtime/'rollup-node20.lock.json').write_text(json.dumps({'url':base+name,'sha256':checksum,'filename':name,'official_checksum_url':base+'SHASUMS256.txt','official_checksum_document_sha256':hashlib.sha256(response.content).hexdigest(),'role':'bootstrap for unchanged Rollup4.40.2 upstream Node module-format warning semantics; not B05 target artifact'},indent=2)+'\n')
(runtime/'Dockerfile.rollup-node20').write_text('FROM sbench-build-runtime:v21\nUSER root\nCOPY '+name+' /tmp/node20.tar.xz\nRUN mkdir -p /opt/bootstrap/node20 && tar -xJf /tmp/node20.tar.xz --strip-components=1 -C /opt/bootstrap/node20 && rm /tmp/node20.tar.xz && rm -rf /opt/bootstrap/node && ln -s /opt/bootstrap/node20 /opt/bootstrap/node\n')
with (ROOT/'runs/runtime_rollup_node20.log').open('w') as log:
 subprocess.run(['docker','build','--memory=12g','--memory-swap=12g','--cpu-period=100000','--cpu-quota=200000','--label','sbench.build.runtime=true','-t','sbench-build-runtime:rollup-node20','-f',str(runtime/'Dockerfile.rollup-node20'),str(runtime)],env={**os.environ,'DOCKER_BUILDKIT':'0'},stdout=log,stderr=subprocess.STDOUT,timeout=600,check=True)
p=runtime/'policy.json';d=json.loads(p.read_text());d['task_image_overrides']['BUILDv1-E07']='sbench-build-runtime:rollup-node20';d['rollup_bootstrap_node_version']='20.18.3';p.write_text(json.dumps(d,indent=2)+'\n')
print('GENUINE_ROLLUP_NODE20_BOOTSTRAP_READY',checksum,flush=True)
