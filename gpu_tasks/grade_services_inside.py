"""Independent full-output and fresh HTTP model checks; no agent grading code."""
import json,sys,time,subprocess,urllib.request,socket,runpy
from pathlib import Path
import numpy as np
import torch
from transformers import AutoTokenizer,AutoModel,AutoModelForSequenceClassification

tid=sys.argv[1];out=Path('/artifacts/output');Path('evaluation').mkdir(exist_ok=True)
embedding=tid.endswith('D08')
repo='/models/'+('sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2' if embedding else 'cross-encoder--ms-marco-MiniLM-L6-v2')
tokenizer=AutoTokenizer.from_pretrained(repo)
model=(AutoModel if embedding else AutoModelForSequenceClassification).from_pretrained(repo).cuda().eval()
def expected(payload):
    with torch.no_grad():
        if embedding:
            batch=tokenizer(payload['texts'],padding=True,truncation=True,max_length=128,return_tensors='pt').to('cuda')
            h=model(**batch).last_hidden_state;m=batch['attention_mask'].unsqueeze(-1)
            return torch.nn.functional.normalize((h*m).sum(1)/m.sum(1),dim=1).cpu().numpy()
        batch=tokenizer([payload['query']]*len(payload['passages']),[p['text'] for p in payload['passages']],padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda')
        return model(**batch).logits.flatten().cpu().numpy()
report={'task_id':tid,'passed':False,'reference_large_tested':False}
if embedding:
    rows=[json.loads(x) for x in Path('input/documents.jsonl').read_text().splitlines()]
    vectors=np.load(out/'embeddings.npy');assert vectors.shape==(len(rows),384)
    ids=json.loads((out/'document_ids.json').read_text());assert ids==[x['id'] for x in rows]
    ref=np.concatenate([expected({'texts':[x['text'] for x in rows[i:i+16]]}) for i in range(0,len(rows),16)])
    error=float(np.abs(ref-vectors).max());assert error<1e-5,error
    assert np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5)
    report.update(documents=len(rows),max_reference_error=error)
    fresh={'texts':['The new scientific report discusses water quality.','هذه فقرة جديدة عن المياه.','यह जल की गुणवत्ता पर नया वाक्य है।']};endpoint='/encode'
    cli=['encode','--input','input/documents.jsonl','--output','evaluation/profile']
else:
    rows=[json.loads(x) for x in Path('input/requests.jsonl').read_text().splitlines()]
    predictions=[json.loads(x) for x in (out/'rankings.jsonl').read_text().splitlines()]
    assert [x['query_id'] for x in predictions]==[x['id'] for x in rows]
    error=0;total=0
    for row,pred in zip(rows,predictions):
        ref=expected(row);scores=dict(zip([p['id'] for p in row['passages']],ref));rank=pred['rankings']
        assert len(rank)==len(scores) and set(x['id'] for x in rank)==set(scores)
        error=max(error,max(abs(x['raw_score']-float(scores[x['id']])) for x in rank));total+=len(rank)
        assert [x['id'] for x in rank]==sorted(scores,key=lambda k:(-float(scores[k]),k))
    assert error<1e-4,error
    report.update(queries=len(rows),candidate_pairs=total,max_reference_error=error)
    fresh={'query':'What does a river carry?','passages':[{'id':'f1','text':'Rivers carry water and sediment.'},{'id':'f2','text':'A satellite orbits the planet.'}]};endpoint='/rerank'
    cli=['run','--input','input','--output','evaluation/profile']
reference=expected(fresh)
del model;torch.cuda.empty_cache()
log=open('evaluation/server.log','w')
proc=subprocess.Popen(['python','/artifacts/solution/main.py','serve','--port','8129'],stdout=log,stderr=log)
def request(path,payload=None):
    req=urllib.request.Request('http://127.0.0.1:8129'+path,data=json.dumps(payload).encode() if payload else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
try:
    ready=None
    for _ in range(120):
        if proc.poll() is not None:raise AssertionError('service exited: '+Path('evaluation/server.log').read_text()[-3000:])
        try:ready=request('/health');break
        except Exception:time.sleep(.25)
    assert ready and 'cuda' in json.dumps(ready).lower(),ready
    for round_idx in range(2):
        reply=request(endpoint,fresh)
        if embedding:
            vals=np.asarray(reply['embeddings']);assert vals.shape==reference.shape and np.allclose(vals,reference,atol=1e-5)
        else:
            ranks=reply['rankings'];vals={r['id']:r['raw_score'] for r in ranks}
            assert set(vals)==set(p['id'] for p in fresh['passages'])
            assert all(abs(vals[p['id']]-float(v))<1e-4 for p,v in zip(fresh['passages'],reference))
        if round_idx==0:time.sleep(3)
    report.update(fresh_service_rounds=2,idle_seconds=3)
finally:
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait();raise AssertionError('SIGTERM did not cleanly stop server')
    log.close()
assert proc.returncode==0,proc.returncode
with socket.socket() as sock:
    sock.settimeout(1)
    assert sock.connect_ex(('127.0.0.1',8129))!=0,'listener remains after SIGTERM'
sys.path.insert(0,'/artifacts/solution');sys.argv=['/artifacts/solution/main.py']+cli
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
    try:runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
    except SystemExit as e:assert e.code in (None,0)
    torch.cuda.synchronize()
events=[e for e in prof.events() if e.device_type==torch.autograd.DeviceType.CUDA];assert len(events)>100
report.update(passed=True,cuda_kernel_events=len(events),sigterm_exit_code=proc.returncode)
Path('evaluation/results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
