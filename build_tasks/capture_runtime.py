"""Read package and wheel inventories inside a bounded, read-only container."""
import json
from pathlib import Path
import subprocess

from container import ROOT, Sandbox

SCRIPT='''
from pathlib import Path
import hashlib,json,subprocess
p=Path('/workspace/output');p.mkdir(exist_ok=True)
commands={"system_packages.txt":["dpkg-query","-W"],"python_packages.txt":["python3","-m","pip","freeze"]}
for name,argv in commands.items():
 result=subprocess.run(argv,capture_output=True,text=True,check=True)
 (p/name).write_text(result.stdout)
inventory=[]
for file in sorted(Path('/opt/wheelhouse').glob('*')):
 if file.is_file():
  with file.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
  inventory.append({'filename':file.name,'bytes':file.stat().st_size,'sha256':checksum})
(p/'wheelhouse.json').write_text(json.dumps(inventory,indent=2))
'''

def capture(task_id: str, label: str) -> None:
    run=ROOT/'runs'/('runtime_inventory_'+label);run.mkdir(parents=True,exist_ok=True)
    script=run/'inventory.py';script.write_text(SCRIPT)
    with Sandbox(task_id,report_dir=run/'isolation') as box:
        box.put(script,'/workspace/inventory.py')
        result=box.exec(['python3','inventory.py'],timeout=180)
        assert result['exit_code']==0,result
        assert box.collect(run)['collected']
    for file in (run/'output').iterdir():
        if file.is_file():
            import shutil
            shutil.copy2(file,ROOT/'runtime'/((label+'.' if label!='base' else '')+file.name))
    image=json.loads(subprocess.run(['docker','image','inspect',box.policy['image']],capture_output=True,text=True,check=True).stdout)[0]
    (ROOT/'runtime'/((label+'.' if label!='base' else '')+'image_record.json')).write_text(json.dumps({key:image.get(key) for key in ['Id','Created','Architecture','Os','Size','RepoTags','RepoDigests']},indent=2))
    print('RUNTIME_INVENTORY_CAPTURED',image['Id'])

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--task-id',default='runtime-inventory-smoke')
    parser.add_argument('--label',default='base')
    args=parser.parse_args()
    capture(args.task_id,args.label)
