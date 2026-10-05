"""Frozen local-model greedy replay, held-out quality and new calls."""
import ast,json,math,sys,time,subprocess,urllib.request,sqlite3,hashlib,gc,re
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from transformers import AutoTokenizer,AutoModelForCausalLM,AutoProcessor,Qwen2_5_VLForConditionalGeneration

tid=sys.argv[1];kind=tid.split('-')[1];out=Path('/artifacts/output');Path('evaluation').mkdir(exist_ok=True)
report={'task_id':tid,'passed':False,'reference_large_tested':False,'quality_is_separate_from_protocol':True}
reqs=[json.loads(x) for x in Path('input/requests.jsonl').read_text().splitlines()]
files={'D01':'answers.jsonl','D02':'summaries.jsonl','D03':'completions.jsonl','D04':'answers.jsonl','D05':'answers.jsonl','D06':'answers.jsonl','D07':'documents.jsonl','D10':'translations.jsonl'}
rows=[json.loads(x) for x in (out/files[kind]).read_text().splitlines()]
assert len(rows)==(3 if kind=='D06' else len(reqs))
if kind!='D06':assert [str(r['id']) for r in rows]==[str(r['id']) for r in reqs]
model_path='/models/Qwen--Qwen2.5'+('-VL-3B-Instruct' if kind in ['D05','D06','D07'] else '-Coder-0.5B-Instruct' if kind in ['D03','D04'] else '-0.5B-Instruct')
if kind in ['D05','D06','D07']:
    proc=AutoProcessor.from_pretrained(model_path,max_pixels=65536 if kind=='D06' else 262144)
    model=Qwen2_5_VLForConditionalGeneration.from_pretrained(model_path,dtype=torch.bfloat16,attn_implementation='sdpa').cuda().eval();tok=proc.tokenizer
else:
    tok=AutoTokenizer.from_pretrained(model_path);model=AutoModelForCausalLM.from_pretrained(model_path,dtype=torch.bfloat16).cuda().eval();tok.pad_token=tok.eos_token
def chat(system,user):return tok.apply_chat_template([{'role':'system','content':system},{'role':'user','content':user}],tokenize=False,add_generation_prompt=True)
def split_document(system,user,document,budget):
    prefix,suffix=chat(system,user).split('{DOCUMENT}');a=tok(prefix,add_special_tokens=False)['input_ids'];b=tok(suffix,add_special_tokens=False)['input_ids'];d=tok(document,add_special_tokens=False)['input_ids'][:budget-len(a)-len(b) if kind=='D01' else budget]
    return torch.tensor([a+d+b],device='cuda')
def prepare(request,record):
    if kind=='D01':
        x=split_document('You are a careful scientific-paper reading assistant. Answer the question using only the provided document.','Write a high-quality answer for the given question using only the provided search results (some of which might be irrelevant).\n\nDocument:\n{DOCUMENT}\n\nQuestion: '+request['question']+'\nAnswer:',request['document'],2048);return {'input_ids':x,'attention_mask':torch.ones_like(x)},128
    if kind=='D02':
        x=split_document('You are a careful assistant that writes accurate, readable summaries of long U.S. government reports.','Write a concise, faithful summary of the following U.S. government report in 3 to 5 sentences. Keep the main topic, key findings, and any recommendations stated in the report.\n\nReport:\n{DOCUMENT}\n\nSummary:',request['document'],2048);return {'input_ids':x,'attention_mask':torch.ones_like(x)},128
    if kind=='D03':
        prompt=chat('You are a code completion engine. Given a Python function prefix, output only the missing function body. Do not restate the signature or docstring, do not add explanations, and do not use Markdown code fences.','Complete the Python function below by writing only the body code that should be appended after the prefix (keep the 4-space indentation).\n\n'+request['prompt']);assert record['model_input']==prompt
    elif kind=='D04':
        prompt=chat('You are a SQLite SQL expert. Given a database schema and a natural-language question, output exactly one read-only SQLite SELECT query that answers it. Use only tables and columns that exist in the schema. Output the SQL statement alone: no explanation, no markdown fences.','### Database schema\n'+Path('input/schema.sql').read_text()+'\n\n### Question\n'+request['question']+'\n\n### SQL')
    elif kind=='D10':prompt=chat("You are a professional translator. Translate the user's English text into German. Preserve the meaning exactly. Output only the German translation, with no explanations, notes, transliteration or quotation marks.",request['text'])
    if kind in ['D03','D04','D10']:return tok(prompt,return_tensors='pt').to('cuda'),256 if kind in ['D03','D04'] else 128
    images=[]
    if kind=='D06':
        assert record['used_frame_ids']==request['frames'] and len(request['frames'])==8
        for name in request['frames']:
            im=Image.open(Path('input')/name).convert('RGB');w,h=im.size
            if w*h>65536:s=(65536/(w*h))**.5;w,h=int(w*s),int(h*s)
            w,h=max(28,w//28*28),max(28,h//28*28)
            while w*h>65536:
                if w>=h:w-=28
                else:h-=28
            images.append(im.resize((w,h),Image.Resampling.BICUBIC));question=next(q['text'] for q in request['questions'] if str(q['id'])==str(record['questionID']))
        content=[{'type':'image'} for _ in images]+[{'type':'text','text':question}];limit=128
    else:
        im=Image.open(Path('input')/request['image']).convert('RGB')
        if kind=='D05':
            w,h=im.size;hh,ww=max(28,round(h/28)*28),max(28,round(w/28)*28)
            if hh*ww>262144:b=math.sqrt(h*w/262144);hh,ww=max(28,math.floor(h/b/28)*28),max(28,math.floor(w/b/28)*28)
            elif hh*ww<3136:b=math.sqrt(3136/(h*w));hh,ww=math.ceil(h*b/28)*28,math.ceil(w*b/28)*28
            im=im.resize((ww,hh),Image.Resampling.BICUBIC);question=request['question']+"\nAnswer the question with a short phrase taken from the document. If the answer is not present in the image, reply 'unanswerable'.";limit=64
        else:question=json.loads((out/'config.json').read_text())['prompt'];limit=512
        images=[im];content=[{'type':'image'},{'type':'text','text':question}]
    prompt=proc.apply_chat_template([{'role':'user','content':content}],tokenize=False,add_generation_prompt=True);batch=proc(text=[prompt],images=images,return_tensors='pt',padding=kind=='D07').to('cuda')
    if kind=='D05':batch['pixel_values']=batch['pixel_values'].to(torch.bfloat16)
    assert batch['pixel_values'].is_cuda;return batch,limit
counts=[]
for i,record in enumerate(rows):
    request=reqs[0] if kind=='D06' else reqs[i];batch,limit=prepare(request,record);n=batch['input_ids'].shape[1]
    def generate():
        with torch.inference_mode():return model.generate(**batch,max_new_tokens=limit,do_sample=False,num_beams=1,use_cache=True,**({'repetition_penalty':1.0,'eos_token_id':tok.eos_token_id,'pad_token_id':tok.pad_token_id} if kind in ['D02','D03'] else {}))[0,n:].tolist()
    if i==0:
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
            with torch.inference_mode():model(**batch)
            torch.cuda.synchronize()
        counts=[e for e in prof.events() if e.device_type==torch.autograd.DeviceType.CUDA];assert len(counts)>10;report['cuda_kernel_events_reference_replay']=len(counts);del counts,prof;ids=generate()
    else:ids=generate()
    assert ids==record['token_ids'],f'greedy token mismatch at{i}'
    decoded=tok.decode(ids,skip_special_tokens=True).strip();field={'D01':'answer','D02':'summary','D03':'raw_generation','D04':'raw_output','D05':'answer','D06':'answer','D07':'text','D10':'translation'}[kind]
    if field in record:assert decoded==record[field].strip()
    if kind=='D07':assert (out/record['markdown_path']).read_text().strip()==decoded
del model;gc.collect();torch.cuda.empty_cache()
report.update(records=len(rows),all_token_sequences_recomputed=True)
references=json.loads(Path('references.json').read_text()) if Path('references.json').exists() else None
if kind=='D03':
    passed=[]
    for row,ref in zip(rows,references):
        source=row['prompt']+row['completion']+'\n'+ref['test']+'\ncheck('+ref['entry_point']+')\n';p=Path('evaluation/humaneval_case.py');p.write_text(source)
        try:r=subprocess.run(['python','-I',str(p)],timeout=3,capture_output=True);passed.append(r.returncode==0)
        except subprocess.TimeoutExpired:passed.append(False)
    report.update(hidden_pass_at_1=float(np.mean(passed)),hidden_test_passes=passed)
elif kind=='D04':
    db=sqlite3.connect('file:input/chinook.sqlite?mode=ro',uri=True);accurate=[];before=hashlib.sha256(Path('input/chinook.sqlite').read_bytes()).hexdigest()
    for row,ref in zip(rows,references):
        sql=row.get('sql','');ok=False
        if sql and re.match(r'^\s*(SELECT|WITH)\b',sql,re.I):
            try:result=[list(x) for x in db.execute(sql).fetchall()];ok=result==ref['result']
            except sqlite3.Error:pass
        accurate.append(ok)
    assert hashlib.sha256(Path('input/chinook.sqlite').read_bytes()).hexdigest()==before
    report['execution_accuracy']=float(np.mean(accurate))
elif kind=='D05':
    from rapidfuzz.distance import Levenshtein
    scores=[]
    for row,refs in zip(rows,references):
        text=row['answer'].lower().strip();best=0
        for ref in refs:
            ref=ref.lower().strip();v=Levenshtein.distance(text,ref)/max(len(text),len(ref),1);best=max(best,1-v if v<.5 else 0)
        scores.append(best)
    report['anls']=float(np.mean(scores))
elif kind=='D10':
    import sacrebleu
    report['bleu']=sacrebleu.corpus_bleu([r['translation'] for r in rows],[references]).score;report['chrf']=sacrebleu.corpus_chrf([r['translation'] for r in rows],[references]).score
elif kind in ['D01','D02','D07']:report['quality_limitation']='Formal accuracy/ROUGE/layout scoring remains unvalidated; debug checks full coverage and genuine generation.'
else:report['quality_limitation']='Temporal understanding requires an independent content review; no Video-MME score.'
# A new call uses a source-native image/frame where applicable, a new question/text,
# and a fresh process; the original delivered answer directory stays read-only.
new_text='The city library will reopen on Monday after repairs.'
if kind in ['D01','D02','D03']:
    args=['serve','--port','8163'];endpoint='/complete' if kind=='D03' else '/infer'
    payload={'id':'new-evaluation-call','prompt':'def double_value(number):\n    """Return twice the supplied number."""\n'} if kind=='D03' else {'id':'new-evaluation-call','document':new_text,'question':'When will the library reopen?'}
    log=open('evaluation/service.log','w');child=subprocess.Popen(['python','/artifacts/solution/main.py']+args,stdout=log,stderr=log)
    try:
        ready=False
        for _ in range(120):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8163/health',timeout=1) as r:health=json.load(r);ready=True;break
            except Exception:time.sleep(.25)
        assert ready and child.poll() is None,Path('evaluation/service.log').read_text()[-2000:]
        replies=[]
        for _ in range(2):
            request=urllib.request.Request('http://127.0.0.1:8163'+endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=30) as r:reply=json.load(r)
            assert isinstance(reply,dict) and reply.get('token_ids',reply.get('result',{}).get('token_ids')) is not None;replies.append(reply);time.sleep(2)
        assert replies[0]==replies[1] or replies[0].get('token_ids')==replies[1].get('token_ids')
    finally:child.terminate();child.wait(timeout=10);log.close()
    assert child.returncode==0;report.update(new_requests=2,idle_reuse=True,sigterm_clean=True)
else:
    if kind=='D04':args=['query','--database','input/chinook.sqlite','--question','How many artists are in the database?','--output','evaluation/new.json']
    elif kind=='D05':args=['infer','--image','input/'+reqs[0]['image'],'--question','What is the main heading of this document?','--output','evaluation/new.json']
    elif kind=='D07':args=['infer','--image','input/'+reqs[0]['image'],'--prompt','Transcribe the first visible paragraph.','--output','evaluation/new.json']
    elif kind=='D10':args=['translate','--text',new_text,'--source-language','English','--target-language','German','--output','evaluation/new.json']
    else:
        new=dict(reqs[0]);new['questions']=[{'id':'new-question','text':'Describe the visible road boundary.'}];new['frames']=[str(Path('/workspace/input')/x) for x in new['frames']];Path('evaluation/new_requests.jsonl').write_text(json.dumps(new)+'\n');args=['infer','--input','evaluation/new_requests.jsonl','--output','evaluation/new']
    result=subprocess.run(['python','/artifacts/solution/main.py']+args,capture_output=True,text=True,timeout=90);assert result.returncode==0,result.stdout+result.stderr;assert any(p.stat().st_size>10 for p in Path('evaluation').glob('new*'));report['fresh_process_request']=True
report['passed']=True;Path('evaluation/results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
