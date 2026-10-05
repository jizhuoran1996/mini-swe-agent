"""Execute authored recipes only in bounded containers and preserve every attempt."""
import argparse
import fcntl
import json
from pathlib import Path
import shlex
import time
from container import ROOT, Sandbox
from status import update


def run_task(task_id, compile_only=False):
    task = ROOT / 'tasks' / task_id
    with (task / 'execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = json.loads((task / 'latest_run.json').read_text())
        if current.get('solver_execution_completed') and current.get('execution', {}).get('exit_code') == 0:
            print('EXECUTION_ALREADY_COMPLETED', task_id, flush=True)
            return current
        return execute_task(task_id, compile_only)


def execute_task(task_id, compile_only=False):
    task = ROOT / 'tasks' / task_id
    source = json.loads((task / 'latest_run.json').read_text())
    authored = Path(source['run_directory'])
    if not authored.is_absolute():
        authored = ROOT / authored
    run = task / 'runs' / (time.strftime('%Y%m%d_%H%M%S') + '_trial_' + str(time.time_ns()))
    run.mkdir(parents=True)
    summary = {**source, 'run_directory': str(run), 'code_source_run': str(authored),
               'built_from_source': False, 'official_tests_passed': False, 'independent_consumer_passed': False}
    solution = authored / 'workspace/solution'
    import shutil
    shutil.copytree(solution, run / 'workspace/solution')
    (run / 'author_delivery.json').write_text((authored / 'author_delivery.json').read_text())
    update(task_id, stage='container_trial_queued', execution_run=str(run))
    with Sandbox(task_id, inputs=task / 'input', report_dir=run / 'isolation') as sandbox:
        update(task_id,stage='container_trial_running')
        sandbox.put(ROOT/'hydrate_dependencies.py','/workspace/hydrate_dependencies.py')
        summary['dependency_preparation']=sandbox.exec(['python3','hydrate_dependencies.py'],timeout=300)
        if summary['dependency_preparation']['exit_code']:
            raise RuntimeError(summary['dependency_preparation']['output'])
        sandbox.put(solution, '/workspace/solution')
        summary['compilation'] = sandbox.exec(['python3','-m','compileall','-q','solution'], timeout=60)
        summary['help'] = sandbox.exec(['python3','solution/main.py','--help'], timeout=60)
        summary['doctor'] = sandbox.exec(['python3','solution/main.py','doctor','--input','input'], timeout=180)
        compiled = summary['compilation']['exit_code'] == 0 and summary['help']['exit_code'] == 0
        summary['container_compile_passed'] = compiled
        if compiled and not compile_only:
            result = sandbox.exec(shlex.split(summary['run_command']))
            summary['execution'] = result
            summary['collected'] = sandbox.collect(run / 'workspace')
            summary['guard_abort'] = sandbox.abort
            completed = result['exit_code'] == 0 and sandbox.abort is None
            summary['solver_execution_completed'] = completed
        else:
            completed = False
    output = run / 'workspace/output'
    if (output / 'commands.json').exists():
        commands = json.loads((output / 'commands.json').read_text())
        summary['phase_wall_seconds'] = {phase: sum(c['wall_seconds'] for c in commands if c['phase'] == phase)
                                          for phase in sorted({c['phase'] for c in commands})}
    summary['built_from_source'] = False
    summary['official_tests_passed'] = False
    summary['independent_consumer_passed'] = False
    (run / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    current=json.loads((task/'latest_run.json').read_text())
    if current['run_directory']!=str(authored):
        current_path=Path(current['run_directory'])
        if not current_path.is_absolute():
            current_path=ROOT/current_path
        same_files=json.loads((current_path/'author_delivery.json').read_text())['files']==json.loads((run/'author_delivery.json').read_text())['files']
        if not same_files or not completed:
            print('HISTORICAL_CONTAINER_TRIAL',task_id,completed,'newer solver preserved',flush=True)
            return summary
    (task / 'latest_run.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    update(task_id, container_compile_passed=compiled,
           stage='execution_completed_awaiting_independent_acceptance' if completed else 'execution_failed' if not compile_only else 'compiled_awaiting_execution',
           execution_exit_code=summary.get('execution', {}).get('exit_code'),
           failure=None if completed else summary.get('guard_abort') or summary.get('execution', {}).get('output', '')[-2000:])
    print('CONTAINER_TRIAL', task_id, 'compile', compiled, 'completed', completed,
          'exit', summary.get('execution', {}).get('exit_code'), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ids', nargs='+')
    parser.add_argument('--compile-only', action='store_true')
    args = parser.parse_args()
    for task_id in args.ids:
        try:
            run_task(task_id, args.compile_only)
        except Exception as error:
            update(task_id, stage='controller_failure', failure=str(error)[-1500:])
            print('CONTROLLER_FAILURE', task_id, type(error).__name__, str(error)[-1500:], flush=True)
