"""Validate complete task coverage, source bindings, and exact Flash file bytes."""
import ast
import hashlib
import json
from pathlib import Path
import shlex

ROOT=Path(__file__).resolve().parent


def validate() -> None:
    expected={f'BUILDv1-{group}{number:02d}' for group in 'ABCDEF' for number in range(1,11)}
    actual={task.name for task in (ROOT/'tasks').iterdir() if task.is_dir()}
    assert actual==expected, 'task coverage differs from six groups of ten'
    for task_id in sorted(expected):
        task=ROOT/'tasks'/task_id
        manifest=json.loads((task/'input/manifest.json').read_text())
        assert manifest['task_id']==task_id and manifest['profile']=='core'
        assert len(manifest['source']['sha256'])==64
        assert manifest['source']['release_ref'] and manifest['scope']
        state=json.loads((task/'latest_run.json').read_text())
        run=Path(state['run_directory'])
        if not run.is_absolute():run=ROOT/run
        delivery=json.loads((run/'author_delivery.json').read_text())
        assert state['model']=='deepseek-flash'
        assert shlex.split(delivery['run_command'])[:3]==['python3','solution/main.py','run']
        for name,content in delivery['files'].items():
            file=run/'workspace'/name
            assert file.read_bytes()==content.encode(), 'export changed Flash-authored source bytes'
            if file.suffix=='.py':ast.parse(content)
        proof=task/'code_provenance.json'
        if proof.exists():
            for name,expected_hash in json.loads(proof.read_text())['files'].items():
                assert hashlib.sha256((run/'workspace/solution'/name).read_bytes()).hexdigest()==expected_hash
        for name in ['TASK.md','source_spec.json','source_brief.md','source_lock.json','original_prompt.md']:
            assert (task/name).stat().st_size>0
    print('VALIDATED60_TASKS_AND_EXACT_FLASH_SOURCE')


if __name__=='__main__':validate()
