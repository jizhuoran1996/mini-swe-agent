import argparse
import json
import sys
from pathlib import Path
from solve_task import solve
from grade_task import grade
from status import ROOT,update

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ids',nargs='+');args=p.parse_args()
    key=sys.stdin.readline().strip()
    for tid in args.ids:
        task=ROOT/'tasks'/tid
        latest=json.loads((task/'latest_run.json').read_text()) if (task/'latest_run.json').exists() else {}
        previous=Path(latest.get('run_directory','/nonexistent'))
        source=previous/'workspace/solution'
        try:
            result=solve(tid,key,resume_run=str(previous) if source.is_dir() else None)
            update(tid,flash_solved=result['solver_declared_complete'],stage='awaiting_independent_evaluation' if result['solver_declared_complete'] else 'solve_failed',failure=result['guard_abort'])
            try:print('RECOVERY_GRADE',tid,json.dumps(grade(tid)),flush=True)
            except ValueError:print('INDEPENDENT_GRADER_PENDING',tid,flush=True)
        except Exception as e:update(tid,stage='execution_error',failure=str(e).replace(key,'[REDACTED]')[-1000:])
