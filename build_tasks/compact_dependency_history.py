"""Discard superseded resolution caches while retaining every current frozen input."""
import json
import re
from pathlib import Path

from prepare_sources import ROOT, sha


def compact() -> None:
    current = {(path.stat().st_dev, path.stat().st_ino)
               for path in (ROOT / 'tasks').glob('*/input/*') if path.is_file()}
    records = []
    for run in sorted((ROOT / 'runs').glob('prepare_*')):
        if not (run / 'result.json').exists():
            continue
        for name in ['bazel-dependencies.tar.gz', 'dependencies.tar.gz']:
            archive = run / 'output' / name
            if not archive.exists() or (archive.stat().st_dev, archive.stat().st_ino) in current:
                continue
            match=re.search(r'BUILDv1-[A-F][0-9]{2}',run.name)
            if not match:continue
            manifest=json.loads((ROOT/'tasks'/match.group()/'input/manifest.json').read_text())
            replacement=next((item for item in manifest.get('dependency_caches',[]) if item['filename']==name),None)
            if not replacement or int(replacement.get('preparation_run','0').rsplit('_',1)[-1])<=int(run.name.rsplit('_',1)[-1]):continue
            records.append({'path': str(archive.relative_to(ROOT)), 'sha256': sha(archive),
                            'bytes': archive.stat().st_size,
                            'reason': 'Superseded resolution cache; current task input retained'})
            archive.unlink()
            print('SUPERSEDED_DEPENDENCY_CACHE_REMOVED', run.name, name, records[-1]['bytes'], flush=True)
    history = ROOT / 'runs/dependency_cache_compaction.json'
    previous = json.loads(history.read_text()) if history.exists() else []
    history.write_text(json.dumps(previous + records, indent=2) + '\n')


if __name__ == '__main__':
    compact()
