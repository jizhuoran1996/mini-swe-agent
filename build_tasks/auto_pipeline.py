"""Repair concrete failures through Flash, separately scheduling real retries."""
import concurrent.futures
import json
import time

from credentials import read_key
from repair_batch import repair
from run import run_task
from status import ROOT, update

key=read_key()
counts={task['id']:task.get('automatic_repair_attempt',0)
        for task in json.loads((ROOT/'progress.json').read_text())['tasks']}
seen=set();authors={};executions={};started=time.monotonic()

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as author_pool, concurrent.futures.ThreadPoolExecutor(max_workers=3) as execution_pool:
    while time.monotonic()-started<12*3600:
        for future,task_id in list(authors.items()):
            if not future.done():continue
            del authors[future]
            try:
                future.result()
            except Exception as error:
                message=str(error).replace(key,'[REDACTED]')[-1800:]
                update(task_id,stage='automated_repair_failed',failure=message)
                print('FLASH_REPAIR_ERROR',task_id,message,flush=True)
                continue
            update(task_id,stage='container_trial_queued')
            executions[execution_pool.submit(run_task,task_id)]=task_id
        for future,task_id in list(executions.items()):
            if not future.done():continue
            del executions[future]
            try:
                future.result()
            except Exception as error:
                update(task_id,stage='controller_failure',failure=str(error)[-1800:])
                print('RETRY_CONTROLLER_ERROR',task_id,str(error)[-1000:],flush=True)
        progress=json.loads((ROOT/'progress.json').read_text())['tasks']
        for task in progress:
            task_id=task['id']
            if len(authors)>=3:break
            if task_id in authors.values() or task_id in executions.values():continue
            if task['stage'] not in ['execution_failed','independent_acceptance_failed']:continue
            if counts.get(task_id,0)>=2:continue
            summary=json.loads((ROOT/'tasks'/task_id/'latest_run.json').read_text())
            if summary.get('guard_abort'):continue
            if summary.get('execution',{}).get('exit_code') not in [1,2] and task['stage']!='independent_acceptance_failed':continue
            identity=(task_id,summary['run_directory'],task['stage'])
            if identity in seen:continue
            seen.add(identity);counts[task_id]=counts.get(task_id,0)+1
            update(task_id,stage='flash_repair_queued',automatic_repair_attempt=counts[task_id])
            authors[author_pool.submit(repair,task_id,key)]=task_id
            print('FLASH_REPAIR',task_id,'attempt',counts[task_id],flush=True)
        time.sleep(5)
