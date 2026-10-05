import json
from pathlib import Path
from container import ROOT,Sandbox
from status import update
import sys,time
for tid in sys.argv[1:]:
 t=ROOT/'tasks'/tid;s=json.loads((t/'latest_run.json').read_text());r=ROOT/'runs'/('smoke_'+tid+'_'+str(time.time_ns()))
 with Sandbox(tid+'-smoke',inputs=t/'input',report_dir=r/'isolation') as b:
  b.put(Path(s['run_directory'])/'workspace/solution','/workspace/solution')
  result={'task_id':tid,'source_code_run':s['run_directory']}
  for name,argv in [('compilation',['python3','-m','compileall','-q','solution']),('help',['python3','solution/main.py','--help']),('doctor',['python3','solution/main.py','doctor','--input','input'])]:result[name]=b.exec(argv,timeout=180)
 result.update(interface_passed=result['compilation']['exit_code']==0 and result['help']['exit_code']==0 and result['doctor']['exit_code'] in [0,78],built_from_source=False,official_tests_passed=False,independent_consumer_passed=False)
 (r/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(t/'latest_smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));update(tid,interface_container_passed=result['interface_passed'],smoke_report=str(r/'result.json'));print('CONTAINER_INTERFACE',tid,result['interface_passed'])
