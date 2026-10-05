"""Execute already Flash-authored code without changing its implementation."""
import argparse,json,shutil,time
from pathlib import Path
from container import ROOT,Sandbox
from status import update

def replay(tid,command):
    task=ROOT/'tasks'/tid;previous=json.loads((task/'latest_run.json').read_text());parent=Path(previous['run_directory'])
    run=task/'runs'/time.strftime('%Y%m%d_%H%M%S');run.mkdir(parents=True);workspace=run/'workspace';workspace.mkdir()
    shutil.copytree(parent/'workspace/solution',workspace/'solution')
    with Sandbox(tid,inputs=task/'input',models=ROOT/'assets/models',report_dir=run/'isolation') as s:
        s.put(workspace/'solution','/workspace/solution');result=s.exec(command);s.collect(workspace);abort=s.abort
    summary={'task_id':tid,'requested_model':'deepseek-flash','authoring_mode':'reexecution_of_unchanged_Flash_authored_code','code_source_run':str(parent),'trial_command':command,'trial_result':result,'run_directory':str(run),'solver_declared_complete':result['exit_code']==0 and abort is None,'guard_abort':abort,'reference_large_tested':False,'independent_evaluation_passed':False,'instance_manifest':json.loads((task/'input/manifest.json').read_text())}
    (run/'summary.json').write_text(json.dumps(summary,indent=2));(task/'latest_run.json').write_text(json.dumps(summary,indent=2));update(tid,stage='execution_completed_awaiting_evaluation' if summary['solver_declared_complete'] else 'solve_failed',flash_solved=summary['solver_declared_complete'],container_tested=False)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('tid');p.add_argument('command');a=p.parse_args();print(json.dumps(replay(a.tid,a.command),indent=2))
