"""Remove duplicate LFS download objects only after checking their frozen bundle."""
import hashlib
import json
from pathlib import Path
import time
import tarfile

from prepare_sources import ROOT, sha


def compact() -> None:
    task = ROOT / 'tasks/BUILDv1-C06'
    deadline = time.monotonic() + 1800
    while True:
        manifest = json.loads((task / 'input/manifest.json').read_text())
        if manifest.get('blender_lfs_objects'):
            break
        assert time.monotonic() < deadline, 'Blender input preparation did not complete'
        time.sleep(2)
    bundle = next(record for record in manifest['dependency_caches']
                  if record['filename'] == 'blender-dependencies.tar.gz')
    path = task / 'input' / bundle['filename']
    assert sha(path) == bundle['sha256']
    expected = {str(Path('blender_modules') / record['module'] / record['path']): record
                for record in manifest['blender_lfs_objects']}
    verified = set()
    with tarfile.open(path) as archive:
        for entry in archive:
            if entry.name not in expected:
                continue
            record = expected[entry.name]
            assert entry.isfile() and entry.size == record['bytes']
            assert hashlib.file_digest(archive.extractfile(entry), 'sha256').hexdigest() == record['oid']
            verified.add(record['oid'])
    assert verified == {record['oid'] for record in expected.values()}
    saved = 0
    for oid in verified:
        duplicate = ROOT / 'assets/blender_lfs' / oid
        if duplicate.exists():
            saved += duplicate.stat().st_size
            duplicate.unlink()
    (ROOT / 'runs/blender_cache_compaction.json').write_text(json.dumps({
        'bundle_sha256': bundle['sha256'], 'verified_lfs_objects': len(verified),
        'duplicate_bytes_removed': saved, 'all_objects_preserved_in_input_bundle': True}, indent=2))
    print('BLENDER_DUPLICATE_CACHE_COMPACTED', len(verified), saved, flush=True)


if __name__ == '__main__':
    compact()
