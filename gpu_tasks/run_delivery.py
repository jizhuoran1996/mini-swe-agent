"""Run an exported Flash delivery or local recorded delivery in the bounded backend."""
import argparse,json,shlex,time
from pathlib import Path
from container import ROOT,Sandbox

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('task_id');p.add_argument('--command');a=p.parse_args();task=ROOT/'tasks'/a.task_id
    manifest=json.loads((task/'input/manifest.json').read_text());gate=manifest.get('assets_ready') is False
    latest=json.loads((task/'latest_run.json').read_text());run=Path(latest['run_directory'])
    if not run.is_absolute():run=ROOT/run
    source=task/'solution' if (task/'solution').exists() else run/'workspace/solution'
    command=a.command or latest.get('trial_command') or (json.loads((task/'delivery.json').read_text()).get('run_command') if (task/'delivery.json').exists() else None)
    if not command and not gate:raise RuntimeError('Specify --command using the TASK.md entry point')
    if command and not command.startswith('python solution/main.py '):raise ValueError('Only the delivered task entry point is accepted')
    directory=task/'runs'/time.strftime('replay_%Y%m%d_%H%M%S');directory.mkdir(parents=True)
    (ROOT/'assets/models').mkdir(parents=True,exist_ok=True)
    with Sandbox(a.task_id,inputs=task/'input',models=ROOT/'assets/models',gpu_enabled=not gate,report_dir=directory/'isolation') as s:
        s.put(source,'/workspace/solution');result=s.exec('python solution/main.py doctor --input input' if gate else command);s.collect(directory/'workspace')
    record={'task_id':a.task_id,'requested_model':'deepseek-flash','trial_command':command,'trial_result':result,'run_directory':str(directory.relative_to(ROOT)),'solver_declared_complete':result['exit_code']==0 and not gate,'guard_abort':s.abort,'reference_large_tested':False,'independent_evaluation_passed':False,'native_assets_gate':gate};(directory/'summary.json').write_text(json.dumps(record,indent=2));(task/'latest_run.json').write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
    raise SystemExit(result['exit_code'] or (78 if gate else 0))
