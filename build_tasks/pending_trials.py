"""Run each newly authored candidate once in its bounded execution lane."""
import concurrent.futures,json,signal,threading,time
from pathlib import Path
from container import Sandbox
from run import run_task
from status import ROOT
stopping=threading.Event()
signal.signal(signal.SIGINT,lambda *_:stopping.set())
signal.signal(signal.SIGTERM,lambda *_:stopping.set())
seen=set();running={}
def lane(task_id):
 box=Sandbox(task_id,report_dir=ROOT/'runs/policy_preview')
 return 'light' if box.light_build else 'small' if box.small_build else 'medium' if box.medium_build else 'heavy'
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 while not stopping.is_set():
  for future,task_id in list(running.items()):
   if not future.done():continue
   del running[future]
   try:future.result()
   except Exception as error:print('PENDING_TRIAL_ERROR',task_id,str(error)[-1500:],flush=True)
  occupied={lane(task_id) for task_id in running.values()}
  for task in sorted((ROOT/'tasks').iterdir()):
   summary=json.loads((task/'latest_run.json').read_text())
   if summary.get('independent_consumer_passed') or summary.get('execution') or task.name in running.values():continue
   identity=(task.name,summary['run_directory'])
   if identity in seen or lane(task.name) in occupied:continue
   seen.add(identity);occupied.add(lane(task.name))
   running[pool.submit(run_task,task.name)]=task.name
   print('PENDING_CANDIDATE_STARTED',task.name,summary['run_directory'],flush=True)
  time.sleep(5)
