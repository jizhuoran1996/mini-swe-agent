"""Check each model-authored interface inside a small container; not a build pass."""
import json
from pathlib import Path
import time
from container import ROOT,Sandbox
from status import update,write_json

for task in sorted((ROOT/'tasks').iterdir()):
    summary=json.loads((task/'latest_run.json').read_text());run=ROOT/'runs'/('smoke_'+task.name+'_'+str(time.time_ns()))
    solution=Path(summary['run_directory'])/'workspace/solution'
    try:
        with Sandbox(task.name+'-smoke',inputs=task/'input',report_dir=run/'isolation') as box:
            box.put(solution,'/workspace/solution')
            syntax=box.exec(['python3','-m','compileall','-q','solution'],timeout=60)
            help=box.exec(['python3','solution/main.py','--help'],timeout=60)
            doctor=box.exec(['python3','solution/main.py','doctor','--input','input'],timeout=180)
        result={'task_id':task.name,'source_code_run':summary['run_directory'],'compilation':syntax,'help':help,'doctor':doctor,
                'interface_passed':syntax['exit_code']==0 and help['exit_code']==0 and doctor['exit_code'] in [0,78],
                'built_from_source':False,'official_tests_passed':False,'independent_consumer_passed':False}
        (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));write_json(task/'latest_smoke.json',result)
        update(task.name,interface_container_passed=result['interface_passed'],smoke_report=str(run/'result.json'))
        print('CONTAINER_INTERFACE',task.name,result['interface_passed'],'doctor',doctor['exit_code'],flush=True)
    except Exception as e:print('SMOKE_ERROR',task.name,str(e)[-1200:],flush=True)
