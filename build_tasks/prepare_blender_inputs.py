"""Lock Blender's gitlinked Linux libraries and genuine test assets, including LFS."""
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import tarfile

import requests

from prepare_sources import ROOT, download, sha

MODULES = [
    ('lib/linux_x64', 'lib-linux_x64', '3cf676e54a5be98285c6d47633fbe1f26929bb5a'),
    ('release/datafiles/assets', 'blender-assets', '0418ad6b8e0d962bde30b2d4d828984b9f9c3299'),
    ('tests/data', 'blender-test-data', '01b8fd393e61e72d6d86d1740c42e82820c3e7a5'),
]


def prepare() -> None:
    task = ROOT / 'tasks/BUILDv1-C06'
    cache = ROOT / 'assets/blender_lfs'
    cache.mkdir(parents=True, exist_ok=True)
    modules, objects = [], []
    for destination, repository, revision in MODULES:
        url = f'https://projects.blender.org/api/v1/repos/blender/{repository}/archive/{revision}.tar.gz'
        archive = ROOT / 'assets/sources' / f'{repository}-{revision[:12]}.tar.gz'
        if repository == 'lib-linux_x64':
            archive = ROOT / 'assets/sources/blender-linux-libs-3cf676e54a5b.tar.gz'
        if not archive.exists():
            download(url, archive)
        module = {'path': destination, 'repository': repository, 'commit': revision,
                  'archive_url': url, 'archive_sha256': sha(archive),
                  'archive': str(archive), 'excluded_paths': ['working/'] if repository == 'blender-assets' else []}
        with tarfile.open(archive) as tree:
            for member in tree:
                parts = Path(member.name).parts[1:]
                if not parts or repository == 'blender-assets' and parts[0] == 'working':
                    continue
                if not member.isfile() or member.size > 1024:
                    continue
                payload = tree.extractfile(member).read()
                if payload.startswith(b'version https://git-lfs.github.com/spec/v1'):
                    values = dict(line.split(' ', 1) for line in payload.decode().splitlines()[1:])
                    objects.append({'module': destination, 'repository': repository,
                                    'path': str(Path(*parts)), 'oid': values['oid'].removeprefix('sha256:'),
                                    'bytes': int(values['size'])})
        modules.append(module)
    assert sum(record['bytes'] for record in objects) < 3 * 2**30

    def fetch(record: dict) -> dict:
        target = cache / record['oid']
        object_url = f"https://projects.blender.org/blender/{record['repository']}.git/info/lfs/objects/{record['oid']}"
        if not target.exists():
            download(object_url, target)
        assert target.stat().st_size == record['bytes'] and sha(target) == record['oid']
        print('BLENDER_LFS_LOCKED', record['module'], record['path'], record['bytes'], flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(fetch, {record['oid']: record for record in objects}.values()))
    records = objects
    lookup = {(record['module'], record['path']): record for record in records}
    bundle = task / 'input/blender-dependencies.tar.gz'
    with tarfile.open(bundle, 'w:gz', compresslevel=1) as output:
        for module in modules:
            with tarfile.open(module['archive']) as tree:
                for member in tree:
                    parts = Path(member.name).parts[1:]
                    if not parts or module['repository'] == 'blender-assets' and parts[0] == 'working':
                        continue
                    relative = str(Path(*parts))
                    assert '..' not in parts and not Path(member.name).is_absolute()
                    entry = copy.copy(member)
                    entry.name = str(Path('blender_modules') / module['path'] / relative)
                    entry.mode &= 0o777
                    lfs = lookup.get((module['path'], relative))
                    if lfs:
                        entry.size = lfs['bytes']
                        with (cache / lfs['oid']).open('rb') as stream:
                            output.addfile(entry, stream)
                    else:
                        output.addfile(entry, tree.extractfile(member) if member.isfile() else None)
    manifest_path = task / 'input/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['dependency_caches'] = [record for record in manifest.get('dependency_caches', [])
                                     if record['filename'] != bundle.name] + [{
        'filename': bundle.name, 'sha256': sha(bundle), 'bytes': bundle.stat().st_size,
        'target_outputs_exported': False, 'destination': '/workspace/cache/blender_modules',
        'contents': 'Official third-party libraries and test assets; no Blender target binary'}]
    for module in modules:
        module.pop('archive')
    manifest['blender_gitlinked_inputs'] = modules
    manifest['blender_lfs_objects'] = records
    manifest['offline_dependencies_ready'] = True
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    verified = set()
    with tarfile.open(bundle) as archive:
        for entry in archive:
            if not entry.isfile():
                continue
            for module in modules:
                prefix = str(Path('blender_modules') / module['path']) + '/'
                if entry.name.startswith(prefix):
                    record = lookup.get((module['path'], entry.name.removeprefix(prefix)))
                    if record:
                        assert entry.size == record['bytes']
                        assert hashlib.file_digest(archive.extractfile(entry), 'sha256').hexdigest() == record['oid']
                        verified.add(record['oid'])
                    break
    assert verified == {record['oid'] for record in records}
    for oid in verified:
        (cache / oid).unlink()
    print('REDUNDANT_LFS_CACHE_REMOVED', len(verified), 'verified objects preserved in locked input bundle', flush=True)
    print('BLENDER_INPUTS_LOCKED', len(records), bundle.stat().st_size, flush=True)


if __name__ == '__main__':
    prepare()
