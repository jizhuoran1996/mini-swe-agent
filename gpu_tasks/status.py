import json
import fcntl
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def update(task_id,**values):
    path=ROOT/'progress.json'
    with (ROOT/'status.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        data=json.loads(path.read_text())
        record=next(x for x in data['tasks'] if x['id']==task_id)
        record.update(values)
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        temporary.replace(path)

def counts():
    data=json.loads((ROOT/'progress.json').read_text())
    return {k:sum(bool(x.get(k)) for x in data['tasks']) for k in ['debug_ready','flash_solved','container_tested','reference_large_tested']}
