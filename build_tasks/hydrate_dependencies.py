"""Verify and unpack prepared dependency caches, without building target code."""
import hashlib
import json
from pathlib import Path
import tarfile
import time


def hydrate(inputs='/workspace/input'):
    inputs=Path(inputs);manifest=json.loads((inputs/'manifest.json').read_text())
    cache=Path('/workspace/cache');cache.mkdir(parents=True,exist_ok=True)
    records=[]
    for item in manifest.get('dependency_caches',[]):
        src=inputs/item['filename'];h=hashlib.sha256()
        with src.open('rb') as f:
            for b in iter(lambda:f.read(4<<20),b''):h.update(b)
        assert h.hexdigest()==item['sha256'],'dependency cache hash mismatch'
        started=time.monotonic()
        with tarfile.open(src) as a:a.extractall(cache,filter='data')
        records.append({'filename':item['filename'],'sha256':item['sha256'],'seconds':time.monotonic()-started})
    Path('/workspace/dependency_preparation.json').write_text(json.dumps(records,indent=2))
    print('verified cache archives',len(records))

if __name__=='__main__':hydrate()
