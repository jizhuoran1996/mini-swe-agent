"""Flash authors complete task implementations; separately controlled container trials.

Compilation, execution and independent acceptance are different evidence fields.
No credential is ever sent into the execution sandbox or written to artifacts.
"""
import argparse,ast,concurrent.futures,json,sys,time,traceback
from pathlib import Path
import requests
from container import ROOT,Sandbox
from status import update
from credentials import read_key

SYSTEM='''You are the authorized DeepSeek Flash solving model. Write a complete usable implementation for the specified GPU task. Return one JSON object {"files":{"solution/main.py":"full Python source","solution/README.md":"usage and honest limitations",...},"run_command":"python solution/main.py ...","notes":"..."}. No Markdown fences. Write the algorithm or a concrete source-native upstream CLI adapter, never a TODO, placeholder, dummy model or random substitute. Do not claim execution: the separate host controller will run your code in a bounded offline container. Follow the frozen TASK.md and input manifest exactly. Original reference-large and declared debug variants are distinct. Use provided local models and genuine assets only. Implement main.py --help without loading models. Also implement main.py doctor --input input: inspect the precise required files and dependencies without executing training/inference; list every missing item, return78 if missing and0 if available. Actual work must require CUDA and fail if unavailable. A source-native adapter for an unavailable asset must contain the complete invocation, state/output handling and checks, and must reject absent inputs before spawning the upstream job; it must never count a missing-input report as a solved task. Use standard official APIs compatible with the stated environment. Do not use mock pretrained weights or CPU fallbacks to satisfy a GPU task. Save full reusable outputs, configuration, real synchronized timings and run.json. Training must use source labels and perform real gradient updates; save optimizer/RNG/state. Do one required run, no hyperparameter searches or ensembles. Do not change task requirements. No host access, network, package installation, sudo, arbitrary shell strings or arbitrary commands from an input manifest. Source and outputs only in solution/ and output/. Prefer less than 400 lines of clear code over a huge framework.'''

def request_files(tid,key,previous=None,error=None):
    task=ROOT/'tasks'/tid
    manifest=(task/'input/manifest.json').read_text() if (task/'input/manifest.json').exists() else 'Assets have not been acquired; implement a strict complete upstream adapter.'
    listing=[str(p.relative_to(task/'input')) for p in (task/'input').rglob('*') if p.is_file()][:100]
    text=(task/'TASK.md').read_text()+'\nINPUT_MANIFEST\n'+manifest+'\nINPUT_FILES\n'+json.dumps(listing)
    if (task/'implementation_contract.json').exists():text+='\n'+(task/'implementation_contract.json').read_text()
    text+='\nREFERENCE SPECIFICATION\n'+(task/'source_spec.json').read_text()
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':text}]
    if previous:
        messages.extend([{'role':'assistant','content':json.dumps(previous,ensure_ascii=False)},{'role':'user','content':'The separate bounded container reported this concrete error. Correct the complete files and return the same JSON schema, retaining all required behavior. Do not change the benchmark contract.\n'+error}])
    last=None
    for attempt in range(3):
        try:
            response=requests.post('https://api.deepseek.com/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':'deepseek-flash','thinking':{'type':'enabled'},'reasoning_effort':'low','max_tokens':49152,'messages':messages},timeout=(15,360))
            if not response.ok:raise RuntimeError('DeepSeek HTTP '+str(response.status_code)+' '+response.text.replace(key,'[REDACTED]')[:400])
            raw=response.json();choice=raw['choices'][0]
            evidence=task/'author_attempts';evidence.mkdir(exist_ok=True)
            (evidence/(str(time.time_ns())+'.json')).write_text(json.dumps(raw,ensure_ascii=False))
            if choice.get('finish_reason')=='length':raise ValueError('response truncated; not a delivery')
            content=choice['message']['content'].strip()
            if content.startswith('```'):content=content.split('\n',1)[1].rsplit('```',1)[0]
            obj=json.loads(content);assert isinstance(obj['files'],dict) and 'solution/main.py' in obj['files'] and 'solution/README.md' in obj['files']
            for name,content in obj['files'].items():
                path=Path(name)
                if path.is_absolute() or '..' in path.parts or path.parts[0]!='solution' or len(content)>128000:raise ValueError('invalid solution file path/size')
                if path.suffix=='.py':ast.parse(content)
            if len(obj['files']['solution/main.py'])<1000:raise ValueError('incomplete implementation')
            command=obj['run_command']
            if not isinstance(command,str) or not command.startswith('python solution/main.py '):raise ValueError('run command must invoke this implementation')
            return obj,raw
        except Exception as e:last=e
    raise last

def author(tid,key):
    task=ROOT/'tasks'/tid;run=task/'runs'/time.strftime('%Y%m%d_%H%M%S');run.mkdir(parents=True,exist_ok=True)
    obj,raw=request_files(tid,key);(run/'author_response.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2))
    workspace=run/'workspace';workspace.mkdir()
    for name,text in obj['files'].items():p=workspace/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    (run/'author_delivery.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    summary={'task_id':tid,'requested_model':'deepseek-flash','authoring_mode':'full_code_JSON_then_separate_container_trial','usage':raw.get('usage'),'run_directory':str(run),'code_authored':True,'solver_declared_complete':False,'independent_evaluation_passed':False,'reference_large_tested':False,'guard_abort':None}
    update(tid,code_authored=True,stage='flash_code_authored')
    with Sandbox(tid+'-compile',inputs=task/'input' if (task/'input').exists() else None,models=ROOT/'assets/models',gpu_enabled=False,report_dir=run/'compile_isolation') as s:
        s.put(workspace/'solution','/workspace/solution')
        compilation=s.exec('python -m compileall -q solution')
        help_result=s.exec('python solution/main.py --help') if compilation['exit_code']==0 else None
        doctor=s.exec('python solution/main.py doctor --input input') if compilation['exit_code']==0 else None
    summary.update(compilation=compilation,help_result=help_result,doctor=doctor,container_compile_passed=compilation['exit_code']==0 and help_result and help_result['exit_code']==0)
    summary['assets_ready_for_trial']=bool(next(x for x in json.loads((ROOT/'progress.json').read_text())['tasks'] if x['id']==tid).get('debug_ready'))
    (run/'summary.json').write_text(json.dumps(summary,indent=2));(task/'latest_run.json').write_text(json.dumps(summary,indent=2))
    update(tid,code_authored=True,container_compile_passed=bool(summary['container_compile_passed']),stage='compiled_awaiting_trial' if summary['assets_ready_for_trial'] else 'compiled_assets_pending',failure=None if summary['container_compile_passed'] else 'container import/CLI check failed')
    print('FLASH_AUTHORED',tid,'compile',summary['container_compile_passed'],'ready',summary['assets_ready_for_trial'],flush=True)
    return summary

def trial(tid,key,repair_limit=2):
    task=ROOT/'tasks'/tid;summary=json.loads((task/'latest_run.json').read_text());run=Path(summary['run_directory']);workspace=run/'workspace';obj=json.loads((run/'author_delivery.json').read_text())
    if not summary.get('assets_ready_for_trial'):
        return {'task_id':tid,'trial':'not admitted: genuine assets pending','container_tested':False}
    trial_revision=str(time.time_ns())
    for attempt in range(repair_limit+1):
        with Sandbox(tid,inputs=task/'input',models=ROOT/'assets/models',report_dir=run/('trial_isolation_'+trial_revision+'_'+str(attempt))) as s:
            s.put(workspace/'solution','/workspace/solution')
            result=s.exec(obj['run_command']);s.collect(workspace);abort=s.abort
        summary.update(trial_command=obj['run_command'],trial_result=result,guard_abort=abort,solver_declared_complete=result['exit_code']==0 and abort is None,execution_attempts=attempt+1)
        (run/f'trial_{trial_revision}_{attempt}.json').write_text(json.dumps(result,indent=2))
        if result['exit_code']==0 or abort or attempt==repair_limit:break
        obj,raw=request_files(tid,key,previous=obj,error=result['output'][-10000:]);(run/f'repair_response_{attempt}.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2))
        for name,text in obj['files'].items():p=workspace/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        (run/'author_delivery.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    (run/'summary.json').write_text(json.dumps(summary,indent=2));(task/'latest_run.json').write_text(json.dumps(summary,indent=2))
    update(tid,flash_solved=summary['solver_declared_complete'],stage='execution_completed_awaiting_evaluation' if summary['solver_declared_complete'] else 'solve_failed',failure=abort or (None if summary['solver_declared_complete'] else result['output'][-1500:]))
    print('FLASH_TRIAL',tid,'executed',summary['solver_declared_complete'],'guard',abort,flush=True);return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['author','trial']);p.add_argument('ids',nargs='+');p.add_argument('--workers',type=int,default=3);a=p.parse_args();key=read_key()
    if not key:raise ValueError('credential required on stdin')
    if a.mode=='author':
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
            futures={pool.submit(author,tid,key):tid for tid in a.ids}
            for f in concurrent.futures.as_completed(futures):
                try:f.result()
                except Exception as e:tid=futures[f];update(tid,stage='authoring_error',failure=str(e).replace(key,'[REDACTED]')[-1500:]);print('AUTHORING_ERROR',tid,type(e).__name__,str(e).replace(key,'[REDACTED]')[:400],flush=True)
    else:
        for tid in a.ids:
            try:trial(tid,key)
            except Exception as e:update(tid,stage='trial_error',failure=str(e).replace(key,'[REDACTED]')[-1500:]);print('TRIAL_ERROR',tid,type(e).__name__,str(e).replace(key,'[REDACTED]')[:400],flush=True)
