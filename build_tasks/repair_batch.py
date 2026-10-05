import argparse
import concurrent.futures
import json
from pathlib import Path
from author import request_files, save
from credentials import read_key
from status import ROOT, update


def repair(task_id,key):
    task=ROOT/'tasks'/task_id
    summary=json.loads((task/'latest_run.json').read_text())
    run=Path(summary['run_directory'])
    if not run.is_absolute():
        run=ROOT/run
    delivery=json.loads((run/'author_delivery.json').read_text())
    feedback=json.dumps({k:summary.get(k) for k in ['compilation','help','doctor','execution','guard_abort','evaluation']},ensure_ascii=False)
    note=ROOT/'feedback'/(task_id+'.md')
    if note.exists():feedback+='\nDESIGNER REVIEW (retain the frozen scope)\n'+note.read_text()
    update(task_id,stage='flash_repair_running')
    fixed,raw=request_files(task_id,key,previous=delivery,feedback=feedback[-30000:])
    return save(task_id,fixed,raw,suffix='repair')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('ids',nargs='+')
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    key=read_key()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures={executor.submit(repair,tid,key):tid for tid in args.ids}
        for future in concurrent.futures.as_completed(futures):
            try:future.result()
            except Exception as error:
                tid=futures[future];message=str(error).replace(key,'[REDACTED]')[-1500:]
                update(tid,stage='flash_repair_failed',failure=message)
                print('REPAIR_FAILED',tid,type(error).__name__,message[:500],flush=True)
