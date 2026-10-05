"""Build the recorded bootstrap environment without unbounded Docker builds."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from prepare_sources import download

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
LAYERS = [
    ('v1','Dockerfile'),('v2','Dockerfile.extra'),('v3','Dockerfile.tools'),
    ('v4','Dockerfile.python'),('v5','Dockerfile.bootstrap'),
    ('v6','Dockerfile.node-tools'),('v7','Dockerfile.node-permissions'),
    ('v8','Dockerfile.dependencies'),('v9','Dockerfile.bazel'),
    ('v10','Dockerfile.rust'),('v11','Dockerfile.python-extra'),
    ('v12','Dockerfile.tf-python'),
]


def prepare() -> None:
    records=[]
    for lock in ['bootstrap-go.lock.json','bootstrap-node.lock.json',
                 'bootstrap-rust.lock.json','bazel.lock.json']:
        data=json.loads((RUNTIME/lock).read_text())
        records.extend(data if isinstance(data,list) else [data])
    for record in records:
        path=RUNTIME/record['filename']
        if not path.exists():
            download(record['url'],path)
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream,'sha256').hexdigest()==record['sha256']
    logs=ROOT/'runs/runtime_rebuild';logs.mkdir(parents=True,exist_ok=True)
    for version,filename in LAYERS:
        with (logs/(version+'.log')).open('w') as log:
            subprocess.run(['docker','build','--memory=12g','--memory-swap=12g',
                            '--cpu-period=100000','--cpu-quota=400000',
                            '--label','sbench.build.runtime=true',
                            '-t','sbench-build-runtime:'+version,
                            '-f',str(RUNTIME/filename),str(RUNTIME)],
                           env={**os.environ,'DOCKER_BUILDKIT':'0'},
                           stdout=log,stderr=subprocess.STDOUT,timeout=7200,check=True)
        print('RUNTIME_LAYER_READY',version,flush=True)


if __name__=='__main__':
    prepare()
