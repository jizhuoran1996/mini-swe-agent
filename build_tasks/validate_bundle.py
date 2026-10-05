"""Validate complete task coverage, source bindings, and exact Flash file bytes."""
import ast
import hashlib
import json
from pathlib import Path
import re
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
        assert json.loads((task/'source_lock.json').read_text())==manifest['source'],'source lock differs from execution manifest'
        binding=re.search(r'## Source and execution binding\s+```json\n(.*?)\n```',(task/'TASK.md').read_text(),re.S)
        expected_binding=dict(manifest)
        if 'blender_lfs_objects' in expected_binding:
            expected_binding['blender_lfs_objects']={'count':len(expected_binding['blender_lfs_objects']),
                                                    'full_records':'input/manifest.json#blender_lfs_objects'}
        assert binding and json.loads(binding.group(1))==expected_binding,'visible task execution binding is stale'
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
        assert {str(file.relative_to(run/'workspace')) for file in (run/'workspace/solution').rglob('*')
                if file.is_file() and '__pycache__' not in file.parts}==set(delivery['files']),'published file set differs from Flash response'
        proof=task/'code_provenance.json'
        if proof.exists():
            for name,expected_hash in json.loads(proof.read_text())['files'].items():
                assert hashlib.sha256((run/'workspace/solution'/name).read_bytes()).hexdigest()==expected_hash
        for name in ['TASK.md','source_spec.json','source_brief.md','source_lock.json','original_prompt.md']:
            assert (task/name).stat().st_size>0
    print('VALIDATED60_TASKS_AND_EXACT_FLASH_SOURCE')


if __name__=='__main__':validate()
