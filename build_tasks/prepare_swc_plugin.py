"""Freeze genuine dependencies used by the unchanged SWC plugin integration test."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

import requests
from container import ROOT, Sandbox
from prepare_sources import download, sha
from status import write_json

SCRIPT = r'''
import hashlib,json,os,tarfile
from pathlib import Path
import buildkit
from hydrate_dependencies import hydrate
hydrate()
s=buildkit.Session('/workspace/input','/workspace/output',jobs=2);s.prepare()
fixture=s.src/'packages/core/e2e/fixtures/plugin_analyze'
lock=fixture/'Cargo.lock';original=hashlib.sha256(lock.read_bytes()).hexdigest()
env={'CARGO_HOME':'/workspace/cache/cargo','CARGO_NET_OFFLINE':'false',
     'CARGO_HTTP_MULTIPLEXING':'false','CARGO_NET_RETRY':'3',
     'CARGO_ENCODED_RUSTFLAGS':''}
s.run(['/opt/bootstrap/rust/bin/cargo','fetch','--manifest-path',str(fixture/'Cargo.toml')],
      cwd=fixture,phase='dependency_resolution',name='plugin_dependency_fetch_no_target_build',env=env,timeout=1800)
s.run(['/opt/bootstrap/rust/bin/cargo','fetch','--locked','--offline','--manifest-path',str(fixture/'Cargo.toml')],
      cwd=fixture,phase='dependency_resolution',name='verify_frozen_plugin_dependencies',env={**env,'CARGO_NET_OFFLINE':'true'},timeout=180)
import shutil
shutil.copy2(lock,s.output/'plugin-analyze.Cargo.lock')
with tarfile.open(s.output/'swc-plugin-dependencies.tar.gz','w:gz',compresslevel=1) as archive:
    archive.add('/workspace/cache/cargo',arcname='cargo')
s.write('dependency_resolution.json',{'target_compiled':False,'target_outputs_exported':False,
    'fixture':'packages/core/e2e/fixtures/plugin_analyze','original_lock_sha256':original,
    'resolved_lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),
    'reason':'Original nested lock contains old path-package versions; genuine Cargo resolution updates only dependency locking.'})
'''


def prepare() -> None:
    task = ROOT / 'tasks/BUILDv1-E10'
    name = 'rust-std-nightly-wasm32-wasip1.tar.xz'
    url = 'https://static.rust-lang.org/dist/2024-10-07/' + name
    response = requests.get(url + '.sha256', timeout=60)
    response.raise_for_status()
    expected = response.text.split()[0]
    assert len(expected) == 64
    component = task / 'input' / name
    if not component.exists():
        download(url, component)
    assert sha(component) == expected
    run = ROOT / 'runs' / ('prepare_swc_plugin_' + str(time.time_ns()))
    run.mkdir(parents=True)
    script = run / 'resolve.py'; script.write_text(SCRIPT)
    with Sandbox('BUILDv1-E10-prepare', inputs=task / 'input', report_dir=run / 'isolation', preparation=True) as box:
        box.put(ROOT / 'hydrate_dependencies.py', '/workspace/hydrate_dependencies.py')
        box.put(script, '/workspace/resolve.py')
        result = box.exec(['python3', 'resolve.py'], timeout=2200)
        collected = box.collect(run)
    write_json(run / 'result.json', result)
    assert result['exit_code'] == 0 and collected['collected'], result
    archive = run / 'output/swc-plugin-dependencies.tar.gz'
    target = task / 'input' / archive.name
    target.hardlink_to(archive)
    resolved = run / 'output/plugin-analyze.Cargo.lock'
    lock_target = task / 'input' / resolved.name
    lock_target.hardlink_to(resolved)
    path = task / 'input/manifest.json'; manifest = json.loads(path.read_text())
    manifest['dependency_caches'] += [
        {'filename': target.name, 'sha256': sha(target), 'bytes': target.stat().st_size,
         'preparation_run': run.name, 'target_outputs_exported': False},
        {'filename': name, 'url': url, 'sha256': expected, 'bytes': component.stat().st_size,
         'official_checksum_url': url + '.sha256', 'target_outputs_exported': False,
         'purpose': 'Genuine wasm32-wasip1 standard library for unchanged official plugin test'}]
    manifest['swc_plugin_fixture_lock'] = {'filename': lock_target.name, 'sha256': sha(lock_target),
        'source_relative_destination': 'packages/core/e2e/fixtures/plugin_analyze/Cargo.lock',
        **json.loads((run / 'output/dependency_resolution.json').read_text())}
    write_json(path, manifest)
    print('GENUINE_SWC_PLUGIN_INPUTS_FROZEN', flush=True)


if __name__ == '__main__':
    prepare()
