import argparse,json,time
from pathlib import Path
from author_batch import request_files,trial
from container import ROOT
from credentials import read_key

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('tid');p.add_argument('--feedback',required=True);a=p.parse_args();key=read_key()
    task=ROOT/'tasks'/a.tid;summary=json.loads((task/'latest_run.json').read_text());run=Path(summary['run_directory']);previous=json.loads((run/'author_delivery.json').read_text()) if (run/'author_delivery.json').exists() else {'files':{str(p.relative_to(run/'workspace')):p.read_text() for p in (run/'workspace/solution').rglob('*') if p.is_file()},'run_command':summary['trial_command']}
    obj,raw=request_files(a.tid,key,previous=previous,error=a.feedback)
    (run/('directed_repair_'+str(time.time_ns())+'.json')).write_text(json.dumps(raw,ensure_ascii=False))
    for name,content in obj['files'].items():
        target=run/'workspace'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
    (run/'author_delivery.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    summary['assets_ready_for_trial']=bool(next(t for t in json.loads((ROOT/'progress.json').read_text())['tasks'] if t['id']==a.tid).get('debug_ready'));(task/'latest_run.json').write_text(json.dumps(summary,indent=2));trial(a.tid,key)
