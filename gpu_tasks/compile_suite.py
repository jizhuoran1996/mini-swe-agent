"""Check all final Flash deliveries together in a CPU-only bounded container."""
import json,shutil,time
from pathlib import Path
from container import ROOT,Sandbox
from status import update

directory=ROOT/'runs/final_compile';directory.mkdir(exist_ok=True)
staging=directory/'deliveries';staging.mkdir(exist_ok=True)
for task in sorted((ROOT/'tasks').iterdir()):
    summary=json.loads((task/'latest_run.json').read_text());source=Path(summary['run_directory'])/'workspace/solution'
    destination=staging/task.name
    if destination.exists():shutil.rmtree(destination)
    shutil.copytree(source,destination)
program='''import subprocess,json,pathlib
results=[]
for p in sorted(pathlib.Path('deliveries').iterdir()):
    compiled=subprocess.run(['python','-m','compileall','-q',str(p)],capture_output=True,text=True,timeout=15)
    help_result=subprocess.run(['python',str(p/'main.py'),'--help'],capture_output=True,text=True,timeout=20)
    results.append({'id':p.name,'compile_exit':compiled.returncode,'help_exit':help_result.returncode,'failure':(compiled.stderr+help_result.stderr)[-1500:] if compiled.returncode or help_result.returncode else None})
    print(p.name,compiled.returncode,help_result.returncode,flush=True)
pathlib.Path('evaluation').mkdir(exist_ok=True);pathlib.Path('evaluation/compilation.json').write_text(json.dumps(results,indent=2))
'''
(directory/'check.py').write_text(program)
with Sandbox('final-cpu-compile',gpu_enabled=False,report_dir=directory/'isolation') as s:
    s.put(staging,'/workspace/deliveries');s.put(directory/'check.py','/workspace/check.py');result=s.exec('python check.py',timeout=300);s.collect(directory,names=('evaluation',))
(directory/'command.json').write_text(json.dumps(result,indent=2))
if result['exit_code']!=0:raise RuntimeError(result['output'])
reports=json.loads((directory/'evaluation/compilation.json').read_text())
for r in reports:update(r['id'],code_authored=True,container_compile_passed=r['compile_exit']==r['help_exit']==0)
assert len(reports)==60;print('Final compiled/CLI-pass:',sum(r['compile_exit']==r['help_exit']==0 for r in reports),'of60')
