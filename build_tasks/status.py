import fcntl
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def update(task_id, **fields):
    with (ROOT / 'status.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = ROOT / 'progress.json'
        data = json.loads(path.read_text())
        next(t for t in data['tasks'] if t['id'] == task_id).update(fields)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(path)


def write_json(path: Path, value: dict) -> None:
    """Replace a complete JSON document without exposing partial writes."""
    import os
    import tempfile
    payload=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    descriptor,temporary=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    with os.fdopen(descriptor,'w') as stream:
        stream.write(payload)
    Path(temporary).replace(path)
