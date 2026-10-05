"""Verify and unpack prepared dependency caches, without building target code."""
import hashlib
import json
import shutil
from pathlib import Path
import tarfile
import time


def cargo_namespace_aliases(cache: Path, task_id: str) -> list[dict[str, str]]:
    if task_id != 'BUILDv1-E10':
        return []
    records = []
    for category in ('index', 'cache', 'src'):
        parent = cache / 'cargo' / 'registry' / category
        prepared = parent / 'index.crates.io-1949cf8c6b5b557f'
        nightly = parent / 'index.crates.io-6f17d22bba15001f'
        assert prepared.is_dir(), f'Missing genuine crates.io cache: {prepared}'
        if nightly.exists() or nightly.is_symlink():
            assert nightly.is_symlink() and nightly.resolve() == prepared.resolve()
        else:
            nightly.symlink_to(prepared.name, target_is_directory=True)
        records.append({'category': category, 'prepared': prepared.name,
                        'nightly': nightly.name, 'same_source': 'https://index.crates.io/',
                        'mapping': 'relative_symlink_to_unmodified_verified_cache'})
    return records


def hydrate(inputs: str = '/workspace/input') -> None:
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
    compatibility = cargo_namespace_aliases(cache, manifest['task_id'])
    if manifest.get('maven_wrapper_bootstrap'):
        shutil.copytree(cache/'maven_wrapper',Path.home()/'.m2/wrapper',dirs_exist_ok=True,symlinks=True)
    Path('/workspace/dependency_preparation.json').write_text(json.dumps(records,indent=2))
    if compatibility:
        Path('/workspace/cargo_cache_namespace_compatibility.json').write_text(
            json.dumps(compatibility, indent=2) + '\n')
    print('verified cache archives',len(records))

if __name__=='__main__':hydrate()
