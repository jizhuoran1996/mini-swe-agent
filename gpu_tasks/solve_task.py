"""DeepSeek Flash solving in the container; credentials only exist in this controller."""
import argparse
import json
from pathlib import Path
import sys
import time

import requests

from container import ROOT, Sandbox

TOOL={"type":"function","function":{"name":"run_shell","description":"Run a command inside your isolated task container at /workspace. Files and GPU work are local to that container. No network is available. Commands time out after 300 seconds.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}}


def solve(task_id,key,turn_limit=12,resume_run=None):
    task=ROOT/"tasks"/task_id
    run=task/"runs"/time.strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True)
    prompt=(task/"TASK.md").read_text()
    usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    messages=[{"role":"system","content":"You are the solving agent. Implement and actually run the task inside the isolated container using run_shell. Commands start in /workspace, Python and the stated dependencies already work there. Do not inspect the host, hidden evaluation material, or API credentials. Use only genuine provided inputs and declared source models. Do not claim unexecuted work passed. The designer has checked GPU/framework availability; inspect input metadata briefly, write your implementation, execute, correct concrete errors, and deliver. Do not repeatedly inspect package signatures, nvidia-smi, hardware or list every installed package. All code in solution/ must be written by you. The evaluator is separate and not available."},{"role":"user","content":prompt}]
    complete=False
    messages[0]['content'] += ' You have at most '+str(turn_limit)+' turns. Do not run hyperparameter searches, ensembles, repeated experiments, or extra training beyond the minimum stated contract. Execute one valid run, fix observed bugs, check reload once, write README, and finish. Keep /tmp below 500 MiB; remove temporary experiments. Training quality metrics are reports, not a reason to keep tuning when the stated acceptance checks pass.'
    start=time.time()
    previous=Path(resume_run) if resume_run else None
    if previous:
        for line in (previous/'trajectory.jsonl').read_text().splitlines():
            row=json.loads(line)
            if row['kind']=='assistant':
                messages.append({k:v for k,v in row['message'].items() if k in ('role','content','tool_calls','reasoning_content')})
            elif row['kind']=='tool':
                messages.append({'role':'tool','tool_call_id':row['tool_call_id'],'content':json.dumps(row['result'],ensure_ascii=False)})
        messages.append({'role':'user','content':'Continue from the restored solution/output artifacts and recorded tool outputs in this fresh container. Finish concrete missing work. Avoid repeating completed benchmark experiments. If all deliverables are already correct, give your concise final delivery now. Environment and immutable inputs are unchanged.'})
    models=ROOT/'assets/models'
    with Sandbox(task_id,inputs=task/"input",models=models if models.exists() else None,artifacts=previous/'workspace' if previous else None,report_dir=run/"isolation") as s:
        s.put(task/"TASK.md","/workspace/TASK.md")
        if previous:
            restored=s.exec('cp -a /artifacts/solution /workspace/solution; if test -d /artifacts/output; then cp -a /artifacts/output /workspace/output; fi')
            if restored['exit_code']:raise RuntimeError('restoring prior artifacts failed: '+restored['output'])
        with (run/"trajectory.jsonl").open("w") as trace:
            for turn in range(1,turn_limit+1):
                print(task_id,"Flash turn",turn,flush=True)
                r=requests.post("https://api.deepseek.com/chat/completions",headers={"Authorization":"Bearer "+key},json={"model":"deepseek-flash","thinking":{"type":"enabled"},"reasoning_effort":"high","max_tokens":16384,"messages":messages,"tools":[TOOL]},timeout=(15,180))
                if not r.ok:raise RuntimeError("DeepSeek request failed: "+str(r.status_code)+" "+r.text.replace(key,"[REDACTED]")[:1000])
                d=r.json()
                (run/f"response_{turn:02}.json").write_text(json.dumps(d,ensure_ascii=False,indent=2))
                for name in usage:usage[name]+=d.get("usage",{}).get(name,0)
                msg=d['choices'][0]['message']
                messages.append({k:v for k,v in msg.items() if k in ('role','content','tool_calls','reasoning_content')})
                trace.write(json.dumps({"kind":"assistant","turn":turn,"elapsed":time.time()-start,"message":msg,"model":d.get('model'),"usage":d.get('usage')},ensure_ascii=False)+"\n");trace.flush()
                if msg.get('content'):print(msg['content'][:500],flush=True)
                calls=msg.get('tool_calls',[])
                if not calls:
                    if d['choices'][0].get('finish_reason')=='length':
                        messages.append({'role':'user','content':'The previous response exhausted the output budget before any tool ran. Write the implementation in smaller chunks with run_shell, then execute it. Do not treat truncated reasoning or a draft as delivery.'})
                        continue
                    complete=True
                    (run/"final.txt").write_text(msg.get('content') or '')
                    break
                for tool in calls:
                    try:
                        command=json.loads(tool['function']['arguments'])['command']
                        result=s.exec(command)
                    except (json.JSONDecodeError,KeyError):
                        command='<invalid or truncated tool arguments>'
                        result={'exit_code':2,'output':'Your tool arguments were not valid JSON (likely output truncation). Split long file writes into smaller commands, then retry. No part of this command ran.','seconds':0,'guard_abort':None}
                    trace.write(json.dumps({"kind":"tool","turn":turn,"tool_call_id":tool['id'],"command":command,"result":result},ensure_ascii=False)+"\n");trace.flush()
                    print("tool",result['exit_code'],round(result['seconds'],2),result['output'][-1400:],flush=True)
                    messages.append({'role':'tool','tool_call_id':tool['id'],'content':json.dumps(result,ensure_ascii=False)})
                    if not s.abort and ('cat >' in command or 'write_text' in command or 'cat <<' in command):
                        s.collect(run/"workspace",names=("solution",))
                    if not s.abort and result['exit_code']==0 and ('solution/main.py' in command or 'output/' in command):
                        s.collect(run/"workspace",names=("solution","output"))
                    if s.abort:break
                if s.abort:break
                if turn==turn_limit-2:
                    messages.append({'role':'user','content':'Two turns remain. Stop optional experiments. Complete the required output files and README, verify one reload if needed, and deliver. Do not remove useful finished artifacts.'})
        s.collect(run/"workspace")
        summary={"task_id":task_id,"requested_model":"deepseek-flash","thinking":"enabled","usage":usage,"wall_seconds":time.time()-start,"solver_declared_complete":complete,"guard_abort":s.abort,"run_directory":str(run),"resumed_from":str(previous) if previous else None,"independent_evaluation_passed":False}
    (run/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    (task/"latest_run.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2),flush=True)
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument('task_id');parser.add_argument('--resume-run');parser.add_argument('--turn-limit',type=int,default=12);args=parser.parse_args()
    key=sys.stdin.readline().strip()
    if not key:raise ValueError('API key must be provided on stdin')
    solve(args.task_id,key,turn_limit=args.turn_limit,resume_run=args.resume_run)
