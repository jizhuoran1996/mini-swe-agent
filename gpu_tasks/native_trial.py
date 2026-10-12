"""Run a prepared native delivery while preserving the original Flash attempt."""
import argparse
import json
from pathlib import Path
import shutil
import time

from container import ROOT, Sandbox
from status import update


def run_trial(task_id, solution, storage, dependencies=None, resume=False, python_env=None):
    task = ROOT / 'tasks' / task_id
    original = json.loads((task / 'latest_run.json').read_text())
    run = storage / 'runs' / task_id / (time.strftime('%Y%m%d_%H%M%S') + '_native_repair')
    (run / 'workspace').mkdir(parents=True)
    shutil.copytree(solution, run / 'workspace/solution', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (run / 'previous_summary.json').write_text(json.dumps(original, indent=2) + '\n')
    summary = {
        'task_id': task_id, 'requested_model': original.get('requested_model'),
        'code_authored': True, 'code_source_run': original.get('code_source_run', original['run_directory']),
        'implementation_repaired_by': 'codex', 'solver_declared_complete': False,
        'independent_evaluation_passed': False, 'reference_large_tested': False,
        'run_directory': str(run), 'dependency_directory': str(dependencies) if dependencies else None,
        'python_environment': str(python_env) if python_env else None,
        'guard_abort': None,
    }
    with Sandbox(task_id, inputs=task / 'input', report_dir=run / 'isolation', dependencies=dependencies, python_env=python_env) as sandbox:
        sandbox.put(run / 'workspace/solution', '/workspace/solution')
        summary['compilation'] = sandbox.exec('python -m compileall -q solution')
        summary['help_result'] = sandbox.exec('python solution/main.py --help')
        summary['doctor'] = sandbox.exec('python solution/main.py doctor --input input')
        ready = all(summary[key]['exit_code'] == 0 for key in ('compilation', 'help_result', 'doctor'))
        summary['container_compile_passed'] = summary['compilation']['exit_code'] == summary['help_result']['exit_code'] == 0
        summary['assets_ready_for_trial'] = ready
        if ready:
            summary['trial_result'] = sandbox.exec('python solution/main.py run --input input --output output')
            if resume and summary['trial_result']['exit_code'] == 0:
                summary['resume_result'] = sandbox.exec('python solution/main.py resume --input input --output output')
            sandbox.collect(run / 'workspace')
        summary['guard_abort'] = sandbox.abort
    (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (task / 'latest_run.json').write_text(json.dumps(summary, indent=2) + '\n')
    update(task_id, stage='native_executed_ungraded' if summary.get('trial_result', {}).get('exit_code') == 0 else 'native_trial_failed',
           debug_ready=summary['assets_ready_for_trial'], container_tested=False,
           failure=summary.get('trial_result', {}).get('output') if summary.get('trial_result', {}).get('exit_code') else None)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('task_id')
    parser.add_argument('--solution', type=Path, required=True)
    parser.add_argument('--storage', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--python-env', type=Path)
    args = parser.parse_args()
    summary = run_trial(args.task_id, args.solution, args.storage, args.dependencies, args.resume, args.python_env)
    print(json.dumps({key: summary.get(key) for key in ('task_id', 'run_directory', 'trial_result', 'resume_result', 'guard_abort')}, indent=2))
