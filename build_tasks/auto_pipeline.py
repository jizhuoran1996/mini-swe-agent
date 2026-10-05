"""Repair concrete failures through Flash, separately scheduling real retries."""
import concurrent.futures
import json
import time
import signal
import threading

from credentials import read_key
from container import Sandbox
from repair_batch import repair
from run import run_task
from status import ROOT, update

stopping=threading.Event()
signal.signal(signal.SIGINT,lambda *_:stopping.set())
signal.signal(signal.SIGTERM,lambda *_:stopping.set())
key=read_key()
counts={task['id']:task.get('automatic_repair_attempt',0)
        for task in json.loads((ROOT/'progress.json').read_text())['tasks']}
seen=set();authors={};executions={};ready=[];started=time.monotonic()


def lane(task_id: str) -> str:
    box=Sandbox(task_id,report_dir=ROOT/'runs/policy_preview')
    return 'small' if box.small_build else 'medium' if box.medium_build else 'heavy'

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as author_pool, concurrent.futures.ThreadPoolExecutor(max_workers=3) as execution_pool:
    while not stopping.is_set() and time.monotonic()-started<12*3600:
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
            ready.append(task_id)
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
            if task_id in authors.values() or task_id in executions.values() or task_id in ready:continue
            if task['stage'] in ['flash_code_authored','container_trial_queued']:
                identity=(task_id,json.loads((ROOT/'tasks'/task_id/'latest_run.json').read_text())['run_directory'],'execute')
                if identity not in seen:
                    seen.add(identity);ready.append(task_id)
                continue
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
        occupied={lane(task_id) for task_id in executions.values()}
        for task_id in ready[:]:
            group=lane(task_id)
            if group in occupied:continue
            ready.remove(task_id);occupied.add(group)
            executions[execution_pool.submit(run_task,task_id)]=task_id
            print('RETRY_LANE_SCHEDULED',task_id,group,flush=True)
        time.sleep(5)
