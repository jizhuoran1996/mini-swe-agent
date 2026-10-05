"""DeepSeek Flash authors project-specific solutions; execution is separately bounded."""
import argparse
import ast
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shlex
import time
import requests
from credentials import read_key
from status import ROOT, update

SYSTEM = '''You are the authorized DeepSeek Flash solver for real engineering build tasks. Return one JSON object {"files":{"solution/main.py":"complete Python implementation","solution/README.md":"usage and honest limitations",...},"run_command":"python3 solution/main.py run --input input --output output --jobs 4","notes":"..."}. No fences. Write a complete usable source-build implementation, not pseudocode, a TODO, an asset checklist, or an invocation with invented options. Follow the frozen CORE profile; it deliberately differs from the original reference scope. Compile the entire declared deliverable from this exact source release, actually run nonempty official upstream tests with preserved expected outputs, then install/package and independently consume your own artifacts outside the source tree. Never substitute a prebuilt target binary or wheel. Bootstrap tools and declared dependency binaries are legitimate inputs but cannot be used as delivered target products. Never downgrade required features or turn a failing test into a skip. Never modify official test expectations. No network, sudo, host access, or package downloads during execution. Preinstalled build tools and build-only bootstrap Python packages are available; target consumer must use newly built artifacts explicitly. Use BUILD_JOBS<=4 and TEST_JOBS<=2; avoid -march=native, unrestricted link concurrency, and infinite fuzzing. Implement --help without a build and doctor --input input listing exact missing source/tool/dependency items, return78 if missing and0 if ready. Your program is executed as an ordinary user in an offline Docker container, read-only root,40GiB RAM/no swap,6 CPUs,24GiB workspace tmpfs,2GiB /tmp,1024 PID,8GiB single-file cap,3-hour deadline. Source archive and manifest are mounted read-only at /workspace/input. All writable work is under /workspace or /tmp. Paths inside containers are /workspace/src,/workspace/build,/workspace/output/install,/workspace/consumer; declare no global HOME changes. Use explicit subprocess argument lists. A trusted helper module buildkit is provided under PYTHONPATH, see its exact source. Use Session(input_dir, output_dir, jobs), .prepare() to safely verify/extract source; .run(argv,cwd,phase,name,env,timeout,check), .test(name,argv,cwd,parser,env,timeout), .write(name,obj), and .finish(features). Every build/configure/install/test/consumer command must use these methods so logs and command exit codes are preserved. .test() records real logs and parses common upstream summaries; where its parser returns null, preserve detailed upstream evidence and report honest target-level coverage, never manufacture case counts. Save exact official test discovery/inventory where available before execution. Session.finish() requires real installed files or a newly built wheel and nonempty test evidence. Python builds use no-build-isolation and local build backends; create a separate consumer venv under /workspace/consumer/venv with no system site packages, install your new wheel using the supplied /opt/wheelhouse dependency wheels and --no-index, then run upstream tests and functional consumers from outside src. Never call Session.finish on a missing-input path. Put supplemental C/Java/Python consumers under solution, compile/run outside src, and assert meaningful semantics. Missing dependencies must fail honestly; the builder may subsequently prepare them and retry. Do not claim you ran anything: the host will execute and independently grade it. Prefer less than350 lines; use the trusted helper for plumbing.''' 


def task_prompt(task_id):
    task = ROOT / 'tasks' / task_id
    spec = json.loads((task / 'source_spec.json').read_text())
    manifest = json.loads((task / 'input/manifest.json').read_text()) if (task / 'input/manifest.json').exists() else {'task_id': task_id, 'profile': 'core', 'source': {'not_acquired': True}, 'scope': spec['scale_plan']['core']}
    if 'blender_lfs_objects' in manifest:
        records=manifest['blender_lfs_objects']
        manifest['blender_lfs_objects']={'count':len(records),
            'records_sha256':hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),
            'full_records':'/workspace/input/manifest.json#blender_lfs_objects'}
    text = 'FROZEN CORE CONTRACT\n' + json.dumps(manifest, ensure_ascii=False, indent=2)
    text += '\nORIGINAL SOURCE-BASED SPECIFICATION (reference and core must remain distinct)\n' + (task / 'source_spec.json').read_text()
    if (task / 'source_context.json').exists():
        context = json.loads((task / 'source_context.json').read_text())
        files = context['official_build_files']
        priority = ['package.json', 'pyproject.toml', 'README.md', 'README', 'CMakeLists.txt', 'Makefile', 'meson.build', 'setup.py', '.gitmodules', 'build/build.py']
        selected = {}
        size = 0
        priority += [name for name in files if name not in priority]
        for name in priority:
            if name in files:
                value = files[name][:22000]
                if size + len(value) <= 50000:
                    selected[name] = value
                    size += len(value)
        text += '\nEXACT OFFICIAL SOURCE CONTEXT\n' + json.dumps({'top_level_paths': context['top_level_paths'], 'files': selected}, ensure_ascii=False)
    text += '\nTRUSTED EXECUTION HELPER (import buildkit; do not duplicate this file)\n' + (ROOT / 'buildkit.py').read_text()
    from container import Sandbox
    policy=Sandbox(task_id,inputs=task/'input',report_dir=ROOT/'runs/policy_preview').policy
    text += '\nEFFECTIVE CONTAINER RESOURCE LIMITS\n'+json.dumps(policy)+'\nThese per-task limits override the general system description.\n'
    text += '\nENVIRONMENT\nUbuntu24.04,gcc13,clang18,cmake3.28,Fortran,autotools,meson1.8.3,ninja,Python3.12,Node22.15/npm10 BOOTSTRAP at /opt/bootstrap/node,Corepack Yarn4.9.1/4.0.2,Go1.23.10 BOOTSTRAP at /opt/bootstrap/go,GOROOT_BOOTSTRAP=/opt/bootstrap/go,Rust1.86.0 BOOTSTRAP at /opt/bootstrap/rust (rustc,cargo,std),target Rust1.87.0 must be compiled from source,OpenJDK21 and17,Maven,BLAS and common image/TLS/database development libraries,real less/re2c/nasm/yasm/libyaml,flatbuffers-compiler/headers and rapidjson. Verified manifest.dependency_caches are hydrated into /workspace/cache before doctor or run; npm cache=/workspace/cache/npm,yarn=/workspace/cache/yarn,Go modules=/workspace/cache/go-mod,Maven=/workspace/cache/maven,Gradle=/workspace/cache/gradle. Do not mock missing tools or alter official fixture/expected behavior. Extra language dependency caches/toolchains may still require preparation; detect those specifically, do not invent their presence. All Python dependency wheels are at /opt/wheelhouse. Source submodules may still require acquisition if .gitmodules is present. Base image target-named system libraries are only dependency inputs; delivered target must be newly built and explicitly selected.\n'
    return text


def request_files(task_id, key, previous=None, feedback=None):
    import contextlib
    import fcntl
    with contextlib.ExitStack() as stack:
        deadline = time.monotonic() + 3600
        while True:
            acquired = None
            for slot in range(3):
                lock = (ROOT / ('flash_api_' + str(slot) + '.lock')).open('a+')
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = lock
                    break
                except BlockingIOError:
                    lock.close()
            if acquired:
                stack.enter_context(acquired)
                return request_files_locked(task_id, key, previous, feedback)
            if time.monotonic() > deadline:
                raise TimeoutError('Flash API concurrency slot deadline exceeded')
            time.sleep(0.25)


def request_files_locked(task_id, key, previous=None, feedback=None):
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': task_prompt(task_id)}]
    if previous:
        messages += [{'role': 'assistant', 'content': json.dumps(previous, ensure_ascii=False)},
                     {'role': 'user', 'content': 'The bounded execution reported the concrete failure below. Correct complete source files without weakening the core contract.\n' + feedback}]
    task = ROOT / 'tasks' / task_id
    attempts = task / 'author_attempts'
    attempts.mkdir(exist_ok=True)
    for attempt in range(3):
        response = requests.post('https://api.deepseek.com/chat/completions', headers={'Authorization': 'Bearer ' + key},
                                 json={'model': 'deepseek-flash', 'thinking': {'type': 'enabled'}, 'reasoning_effort': 'low',
                                       'max_tokens': 49152, 'messages': messages}, timeout=(20, 420))
        if not response.ok:
            raise RuntimeError('DeepSeek HTTP ' + str(response.status_code) + ' ' + response.text.replace(key, '[REDACTED]')[:500])
        raw = response.json()
        (attempts / (str(time.time_ns()) + '.json')).write_text(json.dumps(raw, ensure_ascii=False))
        choice = raw['choices'][0]
        if choice.get('finish_reason') == 'length':
            messages.append({'role': 'user', 'content': 'Prior response was truncated. Return a complete concise JSON delivery using Session for shared plumbing.'})
            continue
        content = choice['message']['content'].strip()
        if content.startswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0]
        try:
            result = json.loads(content)
            assert isinstance(result['files'], dict)
            assert 'solution/main.py' in result['files'] and 'solution/README.md' in result['files']
            for name, source in result['files'].items():
                path = Path(name)
                assert not path.is_absolute() and '..' not in path.parts and path.parts[0] == 'solution'
                assert isinstance(source, str) and len(source) <= 200000
                if path.suffix == '.py':
                    ast.parse(source)
            assert len(result['files']['solution/main.py']) > 1200
            command = shlex.split(result['run_command'])
            assert command[:3] == ['python3', 'solution/main.py', 'run'], 'run_command must start exactly python3 solution/main.py run; the controller runs doctor separately. Return a single argv-style invocation without shell operators, chains, or redirections.'
            return result, raw
        except (ValueError, AssertionError, KeyError, TypeError, SyntaxError) as error:
            messages += [{'role': 'assistant', 'content': content},
                         {'role': 'user', 'content': 'Return valid complete JSON and Python syntax. Validation failure: ' + str(error)[:500]}]
    raise ValueError('no complete valid code delivery in three attempts')


def save(task_id, delivery, raw, suffix='authored'):
    task = ROOT / 'tasks' / task_id
    run = task / 'runs' / (time.strftime('%Y%m%d_%H%M%S') + '_' + suffix + '_' + str(time.time_ns()))
    run.mkdir(parents=True)
    for name, text in delivery['files'].items():
        path = run / 'workspace' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (run / 'author_delivery.json').write_text(json.dumps(delivery, ensure_ascii=False, indent=2))
    (run / 'author_response.json').write_text(json.dumps(raw, ensure_ascii=False))
    summary = {'task_id': task_id, 'model': 'deepseek-flash', 'run_directory': str(run), 'code_authored': True,
               'usage': raw.get('usage'), 'run_command': delivery['run_command'], 'built_from_source': False,
               'official_tests_passed': False, 'independent_consumer_passed': False, 'profile': 'core',
               'reference_tested': False, 'solver_final_event_received': True}
    (run / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (task / 'latest_run.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    update(task_id, stage='flash_code_authored', code_authored=True, latest_run=str(run), built_from_source=False,official_tests_passed=False,independent_consumer_passed=False)
    print('FLASH_AUTHORED', task_id, raw.get('usage', {}).get('total_tokens'), flush=True)
    return summary


def author(task_id, key):
    delivery, raw = request_files(task_id, key)
    return save(task_id, delivery, raw)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ids', nargs='*')
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    key = read_key()
    if not key:
        raise ValueError('authorized credential required on stdin')
    ids = args.ids or [t['id'] for t in json.loads((ROOT / 'progress.json').read_text())['tasks'] if not t['code_authored']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(author, tid, key): tid for tid in ids}
        for future in concurrent.futures.as_completed(futures):
            tid = futures[future]
            try:
                future.result()
            except Exception as error:
                message = str(error).replace(key, '[REDACTED]')[-1500:]
                update(tid, stage='flash_authoring_failed', failure=message)
                print('AUTHORING_FAILED', tid, type(error).__name__, message[:500], flush=True)
