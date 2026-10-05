"""Lock a compatible genuine jtreg harness; the JDK target remains source built."""
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile

import requests

from prepare_sources import ROOT, download, sha


def prepare() -> None:
    task = ROOT / 'tasks/BUILDv1-B10'
    base = 'https://builds.shipilev.net/jtreg/'
    filename = 'jtreg-7.3.1+1.zip'
    checksums = requests.get(base + 'SHA1SUMS', timeout=30)
    checksums.raise_for_status()
    expected = next(line.split()[0] for line in checksums.text.splitlines()
                    if line.split()[-1].lstrip('*') == filename)
    source = ROOT / 'assets/sources' / filename
    if not source.exists():
        download(base + 'jtreg-7.3.1%2B1.zip', source)
    assert hashlib.sha1(source.read_bytes()).hexdigest() == expected
    bundle = task / 'input/jtreg-dependency.tar.gz'
    with zipfile.ZipFile(source) as archive, tarfile.open(bundle, 'w:gz', compresslevel=1) as output:
        for entry in archive.infolist():
            parts = Path(entry.filename).parts
            assert not Path(entry.filename).is_absolute() and '..' not in parts
            if entry.is_dir():
                continue
            info = tarfile.TarInfo(entry.filename)
            info.mode = (entry.external_attr >> 16) & 0o777 or (0o755 if '/bin/' in entry.filename else 0o644)
            info.size = entry.file_size
            with archive.open(entry) as stream:
                output.addfile(info, stream)
    manifest_path = task / 'input/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['dependency_caches'] = [item for item in manifest.get('dependency_caches', [])
                                     if item['filename'] != bundle.name] + [{
        'filename': bundle.name, 'sha256': sha(bundle), 'bytes': bundle.stat().st_size,
        'target_outputs_exported': False, 'destination': '/workspace/cache/jtreg'}]
    manifest['jtreg_harness'] = {'version': '7.3.1+1', 'provider': 'OpenJDK maintainer Aleksey Shipilev',
                                'url': base + 'jtreg-7.3.1%2B1.zip', 'upstream_sha1': expected,
                                'sha256': sha(source), 'path': '/workspace/cache/jtreg',
                                'usage_documentation': base}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('JTREG_HARNESS_LOCKED', filename, source.stat().st_size, flush=True)


if __name__ == '__main__':
    prepare()
