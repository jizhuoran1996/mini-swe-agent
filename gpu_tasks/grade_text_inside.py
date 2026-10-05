import json
from pathlib import Path
import subprocess
import sys
import runpy
import numpy as np
import torch
from transformers import AutoTokenizer,AutoModelForSeq2SeqLM,AutoModelForMaskedLM,AutoModel,BertConfig

tid=sys.argv[1];kind=tid.split('-')[1];out=Path('/artifacts/output')
Path('evaluation').mkdir(exist_ok=True)
rows=[json.loads(x) for x in Path('input/validation.jsonl').read_text().splitlines()]
result={'task_id':tid,'passed':False,'reference_large_tested':False}
checkpoint=out/'checkpoint';tokenizer=AutoTokenizer.from_pretrained(checkpoint)
if kind=='A03':
    model=AutoModelForSeq2SeqLM.from_pretrained(checkpoint,dtype=torch.float32).eval().cuda()
    predictions=[json.loads(x) for x in (out/'translations.jsonl').read_text().splitlines()]
    assert [r['id'] for r in predictions]==[r['id'] for r in rows]
    assert all(r['translation'].strip() for r in predictions)
    reference=AutoModelForSeq2SeqLM.from_pretrained('/models/Helsinki-NLP--opus-mt-en-de',dtype=torch.float32)
    with torch.no_grad():
        batch=tokenizer([r['en'] for r in rows],text_target=[r['de'] for r in rows],max_length=128,truncation=True,padding=True,return_tensors='pt').to('cuda')
        batch['labels'][batch['labels']==tokenizer.pad_token_id]=-100
        loss=float(model(**batch).loss);assert np.isfinite(loss)
    npy_or_file='evaluation/fresh_translations.jsonl'
    # New real sentences absent from the delivered validation predictions.
    training=[json.loads(x) for x in Path('input/train.jsonl').read_text().splitlines()]
    Path('fresh.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in training[5:7]))
    proc=subprocess.run(['python','/artifacts/solution/main.py','translate','--checkpoint',str(checkpoint),'--input','fresh.jsonl','--output',npy_or_file],capture_output=True,text=True,timeout=60)
    assert proc.returncode==0,proc.stdout+proc.stderr
    fresh=[json.loads(x) for x in Path(npy_or_file).read_text().splitlines()];assert len(fresh)==2 and all(x['translation'].strip() for x in fresh)
    result.update(validation_rows=len(rows),teacher_forced_nll=loss,new_sentences=2)
    cli=['translate','--checkpoint',str(checkpoint),'--input','fresh.jsonl','--output','evaluation/profile_translations.jsonl']
else:
    model=AutoModelForMaskedLM.from_pretrained(checkpoint,dtype=torch.float32).eval().cuda()
    original=BertConfig.from_json_file('/models/prajjwal1--bert-tiny/config.json')
    reference=AutoModelForMaskedLM.from_pretrained('/models/prajjwal1--bert-tiny',config=original,dtype=torch.float32)
    vectors=np.load(out/'embeddings.npy');assert vectors.shape==(len(rows),128) and np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5)
    tokens=tokenizer([r['text'] for r in rows],padding=True,truncation=True,max_length=128,return_tensors='pt').to('cuda')
    with torch.no_grad():
        encoded=model.bert(**tokens).last_hidden_state
        mask=tokens['attention_mask'].unsqueeze(-1)
        expected=torch.nn.functional.normalize((encoded*mask).sum(1)/mask.sum(1),dim=1).cpu().numpy()
    assert np.allclose(vectors,expected,atol=1e-5,rtol=1e-5),float(np.abs(vectors-expected).max())
    validation=json.loads((out/'validation_mlm.json').read_text());assert np.isfinite(validation['loss']) and validation['masked_tokens']>0
    proc=subprocess.run(['python','/artifacts/solution/main.py','embed','--checkpoint',str(checkpoint),'--input','input/validation.jsonl','--output','evaluation/reloaded.npy'],capture_output=True,text=True,timeout=60)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert np.allclose(np.load('evaluation/reloaded.npy'),vectors,atol=1e-5,rtol=1e-5)
    result.update(validation_rows=len(rows),embedding_max_reference_error=float(np.abs(vectors-expected).max()),reported_mlm_loss=validation['loss'])
    cli=['embed','--checkpoint',str(checkpoint),'--input','input/validation.jsonl','--output','evaluation/profile_embeddings.npy']
reference_params=dict(reference.named_parameters())
changes=[name for name,p in model.named_parameters() if name in reference_params and not torch.equal(p.detach().cpu(),reference_params[name])]
assert changes
result['changed_parameter_tensors']=len(changes)
state=torch.load(out/'training_state.pt',map_location='cpu',weights_only=False)
assert 'optimizer' in state
del model,reference,state
torch.cuda.empty_cache()
sys.path.insert(0,'/artifacts/solution');sys.argv=['/artifacts/solution/main.py']+cli
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as profile:
    try:runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
    except SystemExit as e:assert e.code in (None,0)
    torch.cuda.synchronize()
events=[e for e in profile.events() if e.device_type==torch.autograd.DeviceType.CUDA]
assert len(events)>100
result.update(passed=True,cuda_kernel_events=len(events))
Path('evaluation/results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
