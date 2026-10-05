"""Grade newly completed executions; preserve evaluator revisions separately."""
import hashlib
import json
from pathlib import Path
import time
from grade import grade_task
from status import ROOT,update

seen=set()
while True:
    revision=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(ROOT.glob('grader_*.py')))).hexdigest()
    for task in sorted((ROOT/'tasks').iterdir()):
        summary=json.loads((task/'latest_run.json').read_text())
        if not summary.get('solver_execution_completed') or summary.get('execution',{}).get('exit_code')!=0:continue
        key=(task.name,summary['run_directory'],revision)
        if key in seen:continue
        seen.add(key)
        try:grade_task(task.name)
        except Exception as e:update(task.name,stage='independent_grader_error',failure=str(e)[-2000:]);print('GRADER_ERROR',task.name,str(e)[-1000:],flush=True)
    time.sleep(5)
