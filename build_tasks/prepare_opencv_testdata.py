"""Freeze genuine OpenCV 4.11 CPU media test fixtures from opencv_extra."""
from input_storage import link_input
import json
from pathlib import Path
import tarfile

from prepare_sources import ROOT, download, sha


def prepare() -> None:
    commit = 'a74cf6bae7fd75d91282b877c559168b3a62148a'
    url = f'https://codeload.github.com/opencv/opencv_extra/tar.gz/{commit}'
    source = ROOT / 'assets/sources/opencv-extra-a74cf6bae7fd.tar.gz'
    if not source.exists():
        download(url, source)
    task = ROOT / 'tasks/BUILDv1-C05'
    bundle = task / 'input/opencv-testdata.tar.gz'
    path = task / 'input/manifest.json'
    manifest = json.loads(path.read_text())
    previous = next((item for item in manifest.get('dependency_caches', [])
                     if item['filename'] == bundle.name), None)
    if previous and bundle.exists():
        history = ROOT / 'assets/dependency_history' / previous['sha256']
        history.parent.mkdir(parents=True, exist_ok=True)
        if not history.exists():
            link_input(history,bundle)
        assert sha(history) == previous['sha256']
        manifest.setdefault('dependency_cache_history', []).append({**previous,
            'preserved_archive': str(history.relative_to(ROOT)), 'valid_previous_selection': True})
    temporary = bundle.with_suffix('.new.tar.gz')
    with tarfile.open(source) as archive, tarfile.open(temporary, 'w:gz', compresslevel=1) as output:
        for member in archive:
            parts = Path(member.name).parts[1:]
            if len(parts) < 2 or parts[0] != 'testdata':
                continue
            assert '..' not in parts
            member.name = str(Path('opencv_extra') / Path(*parts))
            output.addfile(member, archive.extractfile(member) if member.isfile() else None)
    temporary.replace(bundle)
    manifest['dependency_caches'] = [item for item in manifest.get('dependency_caches', [])
                                     if item['filename'] != bundle.name] + [{
        'filename': bundle.name, 'sha256': sha(bundle), 'bytes': bundle.stat().st_size,
        'target_outputs_exported': False, 'destination': '/workspace/cache/opencv_extra/testdata'}]
    manifest['opencv_official_testdata'] = {'repository': 'https://github.com/opencv/opencv_extra',
                                          'release_ref': '4.11.0', 'commit': commit,
                                          'archive_url': url, 'archive_sha256': sha(source),
                                          'selection': 'complete testdata tree, including highgui and stitching siblings',
                                          'path': '/workspace/cache/opencv_extra/testdata'}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('OPENCV_OFFICIAL_TESTDATA_LOCKED', bundle.stat().st_size, flush=True)


if __name__ == '__main__':
    prepare()
