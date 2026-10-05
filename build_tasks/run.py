"""Execute authored recipes only in bounded containers and preserve every attempt."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import time
from container import ROOT, Sandbox
from status import update, write_json
from solution_review import review


def run_task(task_id, compile_only=False, force=False):
    task = ROOT / 'tasks' / task_id
    with (task / 'execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = json.loads((task / 'latest_run.json').read_text())
        if not force and current.get('solver_execution_completed') and current.get('execution', {}).get('exit_code') == 0:
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
    failure=review(task_id,solution)
    if failure:
        (run/'review_rejection.json').write_text(json.dumps({'task_id':task_id,'source_code_run':str(authored),'native_execution_started':False,'passed':False,'failure':failure},indent=2)+'\n')
        update(task_id,stage='solver_review_failed',failure=failure)
        print('REVIEW_REJECTED',task_id,failure,flush=True)
        return {**summary,'review_rejected':True,'failure':failure}
    import shutil
    shutil.copytree(solution, run / 'workspace/solution')
    (run / 'author_delivery.json').write_text((authored / 'author_delivery.json').read_text())
    update(task_id, stage='container_trial_queued', execution_run=str(run),failure=None,execution_exit_code=None)
    with Sandbox(task_id, inputs=task / 'input', report_dir=run / 'isolation') as sandbox:
        selected = json.loads((task / 'latest_run.json').read_text())
        selected_path = Path(selected['run_directory'])
        if not selected_path.is_absolute():
            selected_path = ROOT / selected_path
        selected_files = json.loads((selected_path / 'author_delivery.json').read_text())['files']
        if selected.get('independent_consumer_passed') or selected_files != json.loads((run / 'author_delivery.json').read_text())['files']:
            write_json(run / 'superseded_before_target_execution.json', {
                'task_id': task_id, 'target_execution_started': False,
                'completion_claimed': False, 'selected_run': str(selected_path),
                'reason': 'Selected candidate changed while waiting for the bounded lane'})
            print('SUPERSEDED_BEFORE_EXECUTION', task_id, flush=True)
            return {**summary, 'superseded_before_execution': True}
        update(task_id,stage='container_trial_running')
        hydration_snapshot = run / 'isolation/hydrate_dependencies_snapshot.py'
        shutil.copyfile(ROOT / 'hydrate_dependencies.py', hydration_snapshot)
        sandbox.put(hydration_snapshot, '/workspace/hydrate_dependencies.py')
        summary['dependency_preparation']=sandbox.exec(['python3','hydrate_dependencies.py'],timeout=300)
        if summary['dependency_preparation']['exit_code']:
            raise RuntimeError(summary['dependency_preparation']['output'])
        prepared = sandbox.exec(['python3', '-c', "from pathlib import Path; import json; print(json.dumps({p.name:json.loads(p.read_text()) for p in [Path('/workspace/dependency_preparation.json'),Path('/workspace/cargo_cache_namespace_compatibility.json'),Path('/workspace/bazel_source_repository_reinitialization.json')] if p.exists()}))"], timeout=30)
        assert prepared['exit_code'] == 0
        write_json(run / 'isolation/prepared_input_cache.json', json.loads(prepared['output']))
        sandbox.put(solution, '/workspace/solution')
        summary['compilation'] = sandbox.exec(['python3','-m','compileall','-q','solution'], timeout=60)
        summary['help'] = sandbox.exec(['python3','solution/main.py','--help'], timeout=60)
        summary['doctor'] = sandbox.exec(['python3','solution/main.py','doctor','--input','input'], timeout=180)
        compiled = summary['compilation']['exit_code'] == 0 and summary['help']['exit_code'] == 0
        summary['container_compile_passed'] = compiled
        if compiled and not compile_only:
            collector=None
            if task_id=='BUILDv1-F02':
                from collect_tensorflow_deliverables import start_collection,finish_collection
                collector=start_collection(run,sandbox.name)
            result = sandbox.exec(shlex.split(summary['run_command']))
            summary['execution'] = result
            if collector is not None:
                if result['exit_code']!=0:
                    if not sandbox.abort:sandbox.exec(['touch','/workspace/tensorflow_delivery_cancelled'],timeout=10)
                    collector.terminate()
                summary['artifact_delivery']=finish_collection(run,collector,600)
            (run/'pre_collection_result.json').write_text(json.dumps({'task_id':task_id,'execution':result,'completion_claimed':False,'artifact_collection_pending':True},ensure_ascii=False,indent=2)+'\n')
            destination = run / 'workspace'
            if os.environ.get('SBENCH_BUILD_ARTIFACT_ROOT'):
                destination = Path(os.environ['SBENCH_BUILD_ARTIFACT_ROOT']) / task_id / run.name / 'workspace'
                destination.mkdir(parents=True, exist_ok=False)
                (run / 'workspace/output').symlink_to(destination / 'output', target_is_directory=True)
                write_json(run / 'controller_artifact_location.json', {
                    'original_path': str(run / 'workspace/output'),
                    'backing_path': str(destination / 'output'),
                    'contents_changed': False,
                    'collection': 'Direct collection to configured artifact disk; no duplicate SDK copy'})
            summary['collected'] = ({'collected':False,'artifact_collection_skipped':True,
                                     'reason':'The guard already stopped the container: '+str(sandbox.abort)}
                                    if sandbox.abort else sandbox.collect(destination))
            if destination != run / 'workspace' and (destination / 'artifact_storage.json').exists():
                shutil.copy2(destination / 'artifact_storage.json', run / 'workspace/artifact_storage.json')
            summary['guard_abort'] = sandbox.abort
            completed = result['exit_code'] == 0 and sandbox.abort is None and summary['collected']['collected'] and summary.get('artifact_delivery',{}).get('exit_code',0)==0
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
    write_json(task/'latest_run.json',summary)
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
    parser.add_argument('--force',action='store_true',help='Start a new real trial of the preserved Flash candidate')
    args = parser.parse_args()
    for task_id in args.ids:
        try:
            run_task(task_id, args.compile_only,args.force)
        except Exception as error:
            update(task_id, stage='controller_failure', failure=str(error)[-1500:])
            print('CONTROLLER_FAILURE', task_id, type(error).__name__, str(error)[-1500:], flush=True)
