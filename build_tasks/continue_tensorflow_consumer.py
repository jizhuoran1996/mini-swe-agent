"""Resume the exact Flash consumer after this task's cold build and official tests."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from container import ROOT,Sandbox
from status import update,write_json


def continue_task() -> None:
    task=ROOT/'tasks/BUILDv1-F02'
    selected=json.loads((task/'latest_run.json').read_text())
    authored=Path(selected.get('code_source_run',selected['run_directory']))
    original=task/'runs/20261006_031322_trial_1791227602638975027'
    initial=json.loads((original/'author_delivery.json').read_text())
    revised=json.loads((authored/'author_delivery.json').read_text())
    assert initial['files'].keys()==revised['files'].keys()
    expected=initial['files']['solution/main.py'].replace("'--constraints=%s'","'--constraint=%s'").replace("'--constraint=%s' % constraints,\n                     '--no-deps'] + deps", "'--constraint=%s' % constraints] + deps")
    assert ast.dump(ast.parse(expected))==ast.dump(ast.parse(revised['files']['solution/main.py']))
    assert initial['files']['solution/main.py'].split("    consumer = Path('/workspace/consumer')")[0]==revised['files']['solution/main.py'].split("    consumer = Path('/workspace/consumer')")[0]
    assert all(initial['files'][name]==revised['files'][name] for name in initial['files'] if name!='solution/main.py' and not name.endswith('.md'))
    assert initial['run_command']==revised['run_command']
    outputs=original/'workspace/output'
    commands=json.loads((outputs/'commands.json').read_text())
    assert any(c['phase']=='build' and c['exit_code']==0 for c in commands)
    tests=json.loads((outputs/'tests.json').read_text())
    assert {t['selector']:t['parsed_count'] for t in tests}=={'softmax_op_test':22,'load_test.test_capture_variables':3}
    assert all(t['exit_code']==0 for t in tests)
    assert [c['phase'] for c in commands if c['exit_code']!=0]==['install']
    probe=ROOT/'runs/tf_original_script_xml_preflight_1791231385798721789'
    assert json.loads((probe/'result.json').read_text())['execution']['exit_code']==0
    run=task/'runs'/(time.strftime('%Y%m%d_%H%M%S')+'_trial_consumer_continuation_'+str(time.time_ns()))
    run.mkdir()
    shutil.copytree(authored/'workspace/solution',run/'workspace/solution')
    shutil.copy2(authored/'author_delivery.json',run/'author_delivery.json')
    receipt={'initial_cold_source_build_run':str(original),'final_code_source_run':str(authored),
             'driver_difference':'Only the pip CLI spelling --constraints to --constraint, and enabling real offline transitive dependency resolution for the consumer dependency install; complete AST comparison and byte-identical cold build/test prefix verified; Flash also updated comments and documentation; other executable files are byte-identical.',
             'cold_source_build_repeated':False,'cross_task_artifact_reuse':False,
             'all_original_build_and_test_commands_retained':True,'initial_failed_consumer_retained':True,
             'resumed_stage':'Consumer dependency installation, exact Flash consumer statements and packaging',
             'supplemental_original_test_execution':str(probe),
             'xml_role':'Actual unchanged original test scripts rerun against the same task cold-built wheel in another container; original Bazel22/3 results remain separately retained. XML contains3SavedModelprimarycases and6eager/graphsubtests.'}
    write_json(run/'consumer_continuation.json',receipt)
    script=run/'continue.py'
    script.write_text('''import ast,hashlib,json,os,shutil,sys
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
wheel=next(old.glob('tensorflow_cpu-*.whl'));shutil.copy2(wheel,out/wheel.name)
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
 records.append({'target':target,'path':str(file.relative_to(out)),'sha256':digest(file),'tests':sum(int(x.attrib.get('tests',0)) for x in suites),'failures':sum(int(x.attrib.get('failures',0))+int(x.attrib.get('errors',0)) for x in suites),'primary_cases':sum(' [' not in x.attrib['name'] for x in root.iter('testcase')),'source_script_sha256':source_hash,'execution_role':'Real supplemental execution of the unchanged original source script against the same task cold-built wheel; original Bazel targets already passed and remain separately recorded.'})
bep=out/'bazel_followup_build.bep.json';events=[json.loads(line) for line in bep.read_text().splitlines()];assert any('buildFinished' in e.get('id',{}) and e['finished']['exitCode'].get('code',0)==0 for e in events)
s.write('tensorflow_deliverables.json',{'exit_code':0,'target_outputs_preloaded':False,'consumer_stage_uses_same_task_built_wheel':True,'cross_task_artifact_reuse':False,'bep_sha256':digest(bep),'bep_event_count':len(events),'bep_role':'Real follow-up build in the original cold workspace before the installation failure; only outputs compiled in that same original workspace were reused. This event is preserved byte-for-byte, not regenerated in the consumer continuation.','saved_model_files':[{'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted((out/'saved_model').rglob('*')) if p.is_file()],'original_test_xml':records})
print('EXACT_FLASH_TENSORFLOW_CONSUMER_CONTINUED',flush=True)
''')
    update('BUILDv1-F02',stage='consumer_continuation_running',execution_run=str(run),failure=None)
    with Sandbox('BUILDv1-F02-grade',inputs=task/'input',artifacts=outputs,report_dir=run/'isolation') as box:
        box.put(run/'workspace/solution','/workspace/solution')
        box.put(probe/'output/upstream_test_reports','/workspace/probe_reports')
        box.put(script,'/workspace/continue.py')
        result=box.exec(['python3','continue.py'],timeout=900)
        destination=Path(os.environ.get('SBENCH_BUILD_ARTIFACT_ROOT',ROOT/'runs/artifacts'))/'BUILDv1-F02'/run.name/'workspace'
        destination.mkdir(parents=True)
        (run/'workspace/output').symlink_to(destination/'output',target_is_directory=True)
        collected=box.collect(destination)
    summary={**selected,'run_directory':str(run),'code_source_run':str(authored),'execution':result,
             'solver_execution_completed':result['exit_code']==0 and collected['collected'],
             'collected':collected,'guard_abort':None,'source_build_run':str(original),
             'consumer_continuation':receipt,'built_from_source':False,'official_tests_passed':False,
             'independent_consumer_passed':False}
    write_json(run/'summary.json',summary)
    write_json(task/'latest_run.json',summary)
    update('BUILDv1-F02',stage='execution_completed_awaiting_independent_acceptance' if summary['solver_execution_completed'] else 'consumer_continuation_failed',latest_run=str(run),execution_exit_code=result['exit_code'],failure=None if result['exit_code']==0 else result['output'][-2000:])
    print('GENUINE_TENSORFLOW_CONSUMER_CONTINUATION',result['exit_code'],result['output'][-8000:],flush=True)


if __name__=='__main__':continue_task()
