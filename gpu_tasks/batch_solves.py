import argparse
import json
import sys
import traceback
from solve_task import solve
from grade_task import grade
from status import update,counts

def batch(ids,key):
    results=[]
    for tid in ids:
        update(tid,stage='flash_solving_in_container')
        try:
            result=solve(tid,key)
            update(tid,flash_solved=result['solver_declared_complete'],stage='awaiting_independent_evaluation' if result['solver_declared_complete'] else 'solve_failed',failure=result['guard_abort'])
            try:result['grading']=grade(tid)
            except ValueError as e:result['grading']={'passed':False,'pending':str(e)}
        except Exception as e:
            result={'task_id':tid,'error':str(e).replace(key,'[REDACTED]')[-2000:]}
            update(tid,stage='execution_error',failure=result['error'])
        results.append(result)
        print('BATCH_PROGRESS',json.dumps(counts()),flush=True)
    return results

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('task_ids',nargs='+');args=parser.parse_args()
    from credentials import read_key
    key=read_key()
    if not key:raise ValueError('credential required on stdin')
    batch(args.task_ids,key)
