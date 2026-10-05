"""Freeze Rollup's genuine declared npm SDK consumer dependency."""
from input_storage import link_input
import json
import time
from container import ROOT, Sandbox
from prepare_sources import sha
from status import write_json

SCRIPT = r'''
import json,tarfile
from pathlib import Path
from hydrate_dependencies import hydrate
import buildkit
hydrate()
s=buildkit.Session('/workspace/input','/workspace/output',jobs=2);s.prepare()
dependencies=json.loads((s.src/'package.json').read_text())['dependencies']
assert dependencies['@types/estree']=='1.0.7'
s.run(['npm','cache','add','@types/estree@1.0.7','--cache','/workspace/cache/npm'],cwd=s.src,
      phase='dependency_resolution',name='genuine_estree_npm_metadata_and_tarball',timeout=600)
with tarfile.open(s.output/'rollup-consumer-dependencies.tar.gz','w:gz',compresslevel=1) as archive:
    archive.add('/workspace/cache/npm',arcname='npm')
s.write('dependency_resolution.json',{'target_compiled':False,'target_outputs_exported':False,
    'package':'@types/estree','version':'1.0.7','source':'https://registry.npmjs.org/@types/estree'})
'''


def prepare() -> None:
    task = ROOT / 'tasks/BUILDv1-E07'
    run = ROOT / 'runs' / ('prepare_rollup_consumer_' + str(time.time_ns()))
    run.mkdir(parents=True)
    script = run / 'resolve.py'; script.write_text(SCRIPT)
    with Sandbox('BUILDv1-E07-prepare', inputs=task / 'input', report_dir=run / 'isolation', preparation=True) as box:
        box.put(ROOT / 'hydrate_dependencies.py', '/workspace/hydrate_dependencies.py')
        box.put(script, '/workspace/resolve.py')
        result = box.exec(['python3', 'resolve.py'], timeout=900)
        collected = box.collect(run)
    write_json(run / 'result.json', result)
    assert result['exit_code'] == 0 and collected['collected'], result
    archive = run / 'output/rollup-consumer-dependencies.tar.gz'
    target = task / 'input' / archive.name; link_input(target,archive)
    path = task / 'input/manifest.json'; manifest = json.loads(path.read_text())
    manifest['dependency_caches'] += [{'filename': target.name, 'sha256': sha(target),
        'bytes': target.stat().st_size, 'preparation_run': run.name, 'target_outputs_exported': False}]
    manifest['rollup_consumer_dependencies'] = json.loads((run / 'output/dependency_resolution.json').read_text())
    write_json(path, manifest)
    print('GENUINE_ROLLUP_CONSUMER_DEPENDENCY_FROZEN', flush=True)


if __name__ == '__main__':
    prepare()
