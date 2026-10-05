"""Continue this task's failed consumer after its genuine cold build and tests."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import time
from container import ROOT,Sandbox
from status import update,write_json


def continue_task() -> None:
    task=ROOT/'tasks/BUILDv1-D10'
    selected=json.loads((task/'latest_run.json').read_text())
    authored=Path(selected['run_directory'])
    original=task/'runs/20261006_015823_trial_1791223103579481294'
    initial=json.loads((original/'author_delivery.json').read_text())
    revised=json.loads((authored/'author_delivery.json').read_text())
    assert initial['files']['solution/main.py']==revised['files']['solution/main.py']
    assert initial['files']['solution/envoy_bootstrap.yaml']==revised['files']['solution/envoy_bootstrap.yaml']
    assert initial['run_command']==revised['run_command']
    outputs=original/'workspace/output'
    commands=json.loads((outputs/'commands.json').read_text())
    assert any(c['phase']=='build' and c['exit_code']==0 for c in commands)
    assert all(c['exit_code']==0 for c in commands if c['phase']=='official_test')
    assert [c['phase'] for c in commands if c['exit_code']!=0]==['consumer']
    run=task/'runs'/(time.strftime('%Y%m%d_%H%M%S')+'_trial_consumer_continuation_'+str(time.time_ns()))
    run.mkdir()
    shutil.copytree(authored/'workspace/solution',run/'workspace/solution')
    shutil.copy2(authored/'author_delivery.json',run/'author_delivery.json')
    receipt={'initial_cold_source_build_run':str(original),'final_code_source_run':str(authored),
             'unchanged_build_driver_sha256':hashlib.sha256(revised['files']['solution/main.py'].encode()).hexdigest(),
             'cold_source_build_repeated':False,'cross_task_artifact_reuse':False,
             'all_original_build_and_test_commands_retained':True,
             'initial_failed_consumer_retained':True,'resumed_stage':'HTTP consumer and packaging',
             'basis':'The same task instance already completed its entire initially empty source build and official test. Retry only its failed HTTP header consumer against that exact SDK, then package and independently qualify it.'}
    write_json(run/'consumer_continuation.json',receipt)
    script=run/'continue.py'
    script.write_text('''import json,shutil,sys
from pathlib import Path
from buildkit import Session,digest
out=Path('/workspace/output');old=Path('/artifacts')
s=Session('/workspace/input',out,jobs=2)
s.commands=json.loads((old/'commands.json').read_text());s.tests=json.loads((old/'tests.json').read_text())
s.write('tests.json',s.tests)
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
''')
    update('BUILDv1-D10',stage='consumer_continuation_running',execution_run=str(run),failure=None)
    with Sandbox('BUILDv1-D10-grade',inputs=task/'input',artifacts=outputs,report_dir=run/'isolation') as box:
        box.put(run/'workspace/solution','/workspace/solution')
        box.put(script,'/workspace/continue.py')
        result=box.exec(['python3','continue.py'],timeout=900)
        destination=Path(os.environ.get('SBENCH_BUILD_ARTIFACT_ROOT',ROOT/'runs/artifacts'))/'BUILDv1-D10'/run.name/'workspace'
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
    update('BUILDv1-D10',stage='execution_completed_awaiting_independent_acceptance' if summary['solver_execution_completed'] else 'consumer_continuation_failed',
           latest_run=str(run),execution_exit_code=result['exit_code'],failure=None if result['exit_code']==0 else result['output'][-2000:])
    print('GENUINE_ENV0Y_CONSUMER_CONTINUATION',result['exit_code'],result['output'][-5000:],flush=True)


if __name__=='__main__':
    continue_task()
