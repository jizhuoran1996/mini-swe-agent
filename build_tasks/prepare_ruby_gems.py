"""Freeze Ruby's exact bundled gem source packages from RubyGems.org."""
import concurrent.futures
import json
from pathlib import Path
import tarfile

import requests

from prepare_sources import ROOT, download, sha


def prepare() -> None:
    task = ROOT / 'tasks/BUILDv1-B06'
    manifest_path = task / 'input/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    with tarfile.open(task / 'input' / manifest['source']['filename']) as archive:
        member = next(item for item in archive if item.name.endswith('/gems/bundled_gems'))
        text = archive.extractfile(member).read().decode()
    pairs = [line.split()[:2] for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    cache = ROOT / 'assets/ruby_gems'
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(pair: list[str]) -> dict:
        name, version = pair
        metadata_url = f'https://rubygems.org/api/v2/rubygems/{name}/versions/{version}.json?platform=ruby'
        response = requests.get(metadata_url, timeout=30)
        response.raise_for_status()
        metadata = response.json()
        assert metadata['number'] == version and metadata['platform'] == 'ruby'
        filename = f'{name}-{version}.gem'
        target = cache / filename
        if not target.exists():
            download(metadata['gem_uri'], target)
        assert sha(target) == metadata['sha'], f'RubyGems SHA256 mismatch: {filename}'
        print('OFFICIAL_GEM_LOCKED', filename, target.stat().st_size, flush=True)
        return {'name': name, 'version': version, 'filename': filename,
                'url': metadata['gem_uri'], 'metadata_url': metadata_url,
                'sha256': metadata['sha'], 'bytes': target.stat().st_size,
                'platform': 'ruby', 'target_outputs_exported': False}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(fetch, pairs))
    bundle = task / 'input/ruby-bundled-gems.tar.gz'
    with tarfile.open(bundle, 'w:gz', compresslevel=1) as archive:
        for record in records:
            archive.add(cache / record['filename'], arcname='ruby_gems/' + record['filename'])
    manifest['dependency_caches'] = [record for record in manifest.get('dependency_caches', [])
                                     if record['filename'] != bundle.name] + [{
        'filename': bundle.name, 'sha256': sha(bundle), 'bytes': bundle.stat().st_size,
        'target_outputs_exported': False, 'destination': '/workspace/cache/ruby_gems'}]
    manifest['bundled_gem_sources'] = records
    manifest['offline_dependencies_ready'] = True
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('RUBY_BUNDLED_GEMS_LOCKED', len(records), bundle.stat().st_size, flush=True)


if __name__ == '__main__':
    prepare()
