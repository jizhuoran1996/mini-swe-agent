import json,shutil,sys
from pathlib import Path
from buildkit import Session,digest
out=Path('/workspace/output');old=Path('/artifacts')
s=Session('/workspace/input',out,jobs=2)
s.commands=json.loads((old/'commands.json').read_text());s.tests=json.loads((old/'tests.json').read_text())
for command in s.commands:assert digest(old/command['log'])==command['log_sha256']
shutil.copytree(old/'logs',out/'logs',dirs_exist_ok=True)
shutil.copytree(old/'install',s.install,dirs_exist_ok=True,symlinks=True)
for original in old.glob('*.json'):
 if original.name not in {'commands.json','tests.json','consumer_result.json'}:shutil.copy2(original,out/original.name)
initial=out/'initial_consumer_result.json';shutil.copy2(old/'consumer_result.json',initial)
source=Path('/workspace/solution')
s.run(['python3',str(source/'consumer_check.py'),'--envoy',str(s.install/'bin/envoy'),'--config',str(s.install/'share/envoy/config/bootstrap.yaml'),'--result',str(out/'consumer_result.json')],cwd=s.consumer,phase='consumer',name='single_route_after_flash_header_fix',timeout=900)
result=json.loads((out/'consumer_result.json').read_text());assert result['passed'] is True
s.run([str(s.install/'bin/envoy'),'--version'],cwd=s.consumer,phase='consumer',name='installed_binary_identity',timeout=120)
s.finish(features={'consumer':result,'source_build_and_official_test_already_executed_in_same_task_instance':True,'cross_task_artifact_reuse':False,'source_build_repeated':False})
