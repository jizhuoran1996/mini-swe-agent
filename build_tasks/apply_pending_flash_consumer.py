"""Apply an exact Flash revision to an unused consumer during its source build."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from status import ROOT, update, write_json


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def apply() -> None:
    task = ROOT/'tasks/BUILDv1-F02'
    candidate = json.loads((task/'latest_run.json').read_text())
    authored = Path(candidate['run_directory'])
    progress = json.loads((ROOT/'progress.json').read_text())
    trial = Path(next(row for row in progress['tasks'] if row['id']=='BUILDv1-F02')['execution_run'])
    original = json.loads((trial/'author_delivery.json').read_text())
    revised = json.loads((authored/'author_delivery.json').read_text())
    assert original['run_command']==revised['run_command']
    assert original['files'].keys()==revised['files'].keys()
    changed = [name for name in original['files'] if original['files'][name]!=revised['files'][name]]
    assert changed==['solution/consumer_check.py'], changed
    payload = revised['files'][changed[0]].encode()
    ast.parse(payload)
    main_sha = digest(original['files']['solution/main.py'].encode())
    info = json.loads((trial/'isolation/container.json').read_text())[0]
    assert info['Config']['Labels']['sbench.build.managed']=='true'
    name = info['Name'].removeprefix('/')
    initial_candidates=[path for path in (task/'runs').iterdir()
                        if (path/'author_response.json').exists() and
                        json.loads((path/'author_delivery.json').read_text())==original]
    assert initial_candidates
    receipt = {'initial_code_source_run':str(sorted(initial_candidates)[-1]), 'final_code_source_run':str(authored),
               'initial_author_delivery':'initial_author_delivery.json',
               'file':changed[0], 'initial_sha256':digest(original['files'][changed[0]].encode()),
               'final_sha256':digest(payload), 'unchanged_main_sha256':main_sha,
               'source_and_build_configuration_changed':False, 'official_tests_changed':False,
               'target_outputs_preloaded':False, 'applied_unix':time.time(),
               'basis':'Exact Flash-returned bytes applied before the first consumer invocation; the original cold source build and every official test remain unchanged.'}
    script = '''import ast,hashlib,json,os,sys
from pathlib import Path
receipt=json.loads(sys.argv[1]); output=Path('/workspace/output')
commands=json.loads((output/'commands.json').read_text())
assert not any(command['phase']=='consumer' for command in commands),'consumer already invoked'
assert hashlib.sha256(Path('/workspace/solution/main.py').read_bytes()).hexdigest()==receipt['unchanged_main_sha256']
path=Path('/workspace/solution/consumer_check.py')
assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['initial_sha256']
payload=sys.stdin.buffer.read();ast.parse(payload)
assert hashlib.sha256(payload).hexdigest()==receipt['final_sha256']
temporary=path.with_suffix('.flash-new');temporary.write_bytes(payload);os.replace(temporary,path)
assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['final_sha256']
(output/'flash_consumer_revision.json').write_text(json.dumps(receipt,indent=2)+'\\n')
print('EXACT_FLASH_CONSUMER_APPLIED_BEFORE_FIRST_INVOCATION')
'''
    result = subprocess.run(['docker','exec','-i',name,'python3','-c',script,json.dumps(receipt)],
                            input=payload,capture_output=True,check=True,timeout=30)
    shutil.copy2(trial/'author_delivery.json',trial/'initial_author_delivery.json')
    (trial/'workspace'/changed[0]).write_bytes(payload)
    shutil.copy2(authored/'author_delivery.json',trial/'author_delivery.json')
    write_json(trial/'flash_consumer_revision.json',receipt)
    print(result.stdout.decode().strip(),flush=True)
    deadline = time.monotonic()+10800
    while not (trial/'summary.json').exists():
        if time.monotonic()>deadline:
            raise TimeoutError('native controller did not finalize the revised consumer trial')
        time.sleep(2)
    summary=json.loads((trial/'summary.json').read_text())
    receipt=json.loads((trial/'flash_consumer_revision.json').read_text())
    summary.update(code_source_run=str(authored),usage=candidate['usage'],
                   flash_consumer_revision=receipt)
    write_json(trial/'summary.json',summary)
    selected=json.loads((task/'latest_run.json').read_text())
    if selected['run_directory'] in {str(trial),str(authored)}:
        if selected['run_directory']==str(trial):
            selected.update(code_source_run=str(authored),usage=candidate['usage'],flash_consumer_revision=receipt)
            write_json(task/'latest_run.json',selected)
        elif summary.get('solver_execution_completed'):
            write_json(task/'latest_run.json',summary)
        update('BUILDv1-F02',latest_run=str(trial))
        if not summary.get('solver_execution_completed'):
            update('BUILDv1-F02',stage='execution_failed',execution_exit_code=summary.get('execution',{}).get('exit_code'),
                   failure=summary.get('guard_abort') or summary.get('execution',{}).get('output','')[-2000:])
    print('FLASH_CONSUMER_PROVENANCE_FINALIZED',summary.get('solver_execution_completed'),flush=True)


if __name__=='__main__':
    apply()
