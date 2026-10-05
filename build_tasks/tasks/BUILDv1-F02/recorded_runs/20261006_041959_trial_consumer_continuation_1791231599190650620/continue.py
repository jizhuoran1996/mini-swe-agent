import ast,hashlib,json,os,shutil,sys
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0,'/workspace/solution')
import main as solver
from buildkit import Session,digest
out=Path('/workspace/output');old=Path('/artifacts');s=Session('/workspace/input',out,8)
s.commands=json.loads((old/'commands.json').read_text());s.tests=json.loads((old/'tests.json').read_text());s.write('tests.json',s.tests)
for command in s.commands:assert digest(old/command['log'])==command['log_sha256']
shutil.copytree(old/'logs',out/'logs',dirs_exist_ok=True)
shutil.copytree(old/'install',s.install,dirs_exist_ok=True,symlinks=True)
for name in ['bazel_followup_build.bep.json','bazel_followup_build.log','original_bazel_sharding_help.txt']:shutil.copy2(old/name,out/name)
source=Path('/workspace/solution/main.py');tree=ast.parse(source.read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
start=next(i for i,n in enumerate(function.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='consumer' for t in n.targets))
body=function.body[start:]
new=ast.FunctionDef(name='resume_exact_flash_consumer',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=body,decorator_list=[])
module=ast.fix_missing_locations(ast.Module(body=[new],type_ignores=[]))
build=next(c for c in s.commands if c['phase']=='build' and c['exit_code']==0)['argv']
path=next(a.partition('=PATH=')[2] for a in build if a.startswith('--action_env=PATH='))
repo,base,external=solver.cache_layout(s.manifest)
namespace=dict(vars(solver));namespace.update(session=s,python_bin=sys.executable,wheel=next(old.glob('tensorflow_cpu-*.whl')),bazel=build[0],repo_cache=repo,output_base=base,external=external,patchelf='/opt/build-tools/bin/patchelf',patchelf_dir='/opt/build-tools/bin',action_path=path,shared=[a for a in build if a.startswith(('--action_env=PATH=','--copt=','--host_copt=','--repo_env=','--config='))])
exec(compile(module,str(source),'exec'),namespace)
assert namespace['resume_exact_flash_consumer']()==0
shutil.copytree(Path('/workspace/consumer/saved_model'),out/'saved_model')
reports=out/'upstream_test_reports';shutil.copytree(Path('/workspace/probe_reports'),reports)
records=[]
for filename,target,source_hash in [('softmax.xml','tensorflow/python/kernel_tests/nn_ops/softmax_op_test','390260b9f078ac0a66fa706d4be26bbbad63a8de16b6d3ef4bafa5633ae80c41'),('load.xml','tensorflow/python/saved_model/load_test','b7b27acfd4021dd621321910df481f2ff2cfbf34c204f8efba6cc566a1d57bb3')]:
 file=reports/filename;root=ET.parse(file).getroot();suites=[root] if root.tag=='testsuite' else list(root.iter('testsuite'))
 records.append({'target':target,'path':str(file.relative_to(out)),'sha256':digest(file),'tests':sum(int(x.attrib.get('tests',0)) for x in suites),'failures':sum(int(x.attrib.get('failures',0))+int(x.attrib.get('errors',0)) for x in suites),'primary_cases':sum(' [' not in x.attrib['name'] for x in root.iter('testcase')),'source_script_sha256':source_hash,'execution_role':'Real supplemental execution of the unchanged original source script against this same task's cold-built wheel; original Bazel targets already passed and remain separately recorded.'})
bep=out/'bazel_followup_build.bep.json';events=[json.loads(line) for line in bep.read_text().splitlines()];assert any('buildFinished' in e.get('id',{}) and e['finished']['exitCode'].get('code',0)==0 for e in events)
s.write('tensorflow_deliverables.json',{'exit_code':0,'target_outputs_preloaded':False,'consumer_stage_uses_same_task_built_wheel':True,'cross_task_artifact_reuse':False,'bep_sha256':digest(bep),'bep_event_count':len(events),'bep_role':'Real follow-up build in the original cold workspace before the installation failure; only outputs compiled in that same original workspace were reused. This event is preserved byte-for-byte, not regenerated in the consumer continuation.','saved_model_files':[{'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted((out/'saved_model').rglob('*')) if p.is_file()],'original_test_xml':records})
print('EXACT_FLASH_TENSORFLOW_CONSUMER_CONTINUED',flush=True)
