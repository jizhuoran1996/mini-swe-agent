import importlib.util,json,subprocess,sys,runpy
from pathlib import Path
import numpy as np
import torch
from transformers import AutoTokenizer,AutoModel,AutoModelForCausalLM,BertConfig
from peft import PeftModel

tid=sys.argv[1];short=tid.split('-')[1];out=Path('/artifacts/output');Path('evaluation').mkdir(exist_ok=True)
report={'task_id':tid,'passed':False,'reference_large_tested':False}
if short=='A08':
    from safetensors.torch import load_file
    cfg=json.loads((out/'adapter/adapter_config.json').read_text());assert cfg['r']==8 and set(cfg['target_modules'])=={'q_proj','v_proj'}
    tensors=load_file(out/'adapter/adapter_model.safetensors');assert any('lora_B' in k and v.abs().sum()>0 for k,v in tensors.items())
    base='/models/Qwen--Qwen2.5-0.5B-Instruct';tokenizer=AutoTokenizer.from_pretrained(out/'adapter')
    model=PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(base,dtype=torch.float32),out/'adapter').cuda().eval()
    spec=importlib.util.spec_from_file_location('agent','/artifacts/solution/main.py');agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
    rows=[json.loads(x) for x in Path('input/validation.jsonl').read_text().splitlines()];preds=[json.loads(x) for x in (out/'summaries.jsonl').read_text().splitlines()]
    assert [r['id'] for r in rows]==[r['id'] for r in preds]
    for row,pred in zip(rows,preds):
        ids,_=agent.build_generation_prompt(tokenizer,row['document']);batch=torch.tensor([ids],device='cuda')
        with torch.no_grad():new=model.generate(input_ids=batch,attention_mask=torch.ones_like(batch),do_sample=False,num_beams=1,max_new_tokens=128,repetition_penalty=1.1,pad_token_id=tokenizer.pad_token_id,eos_token_id=tokenizer.eos_token_id)[0,len(ids):].tolist()
        assert new==pred['token_ids']
    del model;torch.cuda.empty_cache()
    state=torch.load(out/'training_state.pt',map_location='cpu',weights_only=False);assert any('optim' in k for k in state)
    report.update(validation_reports=len(rows),adapter_tensors=len(tensors),nonzero_B_tensors=sum('lora_B' in k and bool(v.abs().sum()>0) for k,v in tensors.items()))
    command=['train','--input','input','--output','evaluation/profile_train']
elif short=='A09':
    cp=out/'checkpoint';tokenizer=AutoTokenizer.from_pretrained(cp);model=AutoModel.from_pretrained(cp).cuda().eval()
    rows=[json.loads(x) for x in Path('input/validation.jsonl').read_text().splitlines()]
    errors=[]
    for field,file in [('question','question_embeddings.npy'),('context','passage_embeddings.npy')]:
        tok=tokenizer([r[field] for r in rows],padding=True,truncation=True,max_length=128,return_tensors='pt').to('cuda')
        with torch.no_grad():h=model(**tok).last_hidden_state;m=tok['attention_mask'].unsqueeze(-1);ref=torch.nn.functional.normalize((h*m).sum(1)/m.sum(1),dim=1).cpu().numpy()
        observed=np.load(out/file);assert observed.shape==ref.shape and np.allclose(observed,ref,atol=1e-5);errors.append(float(np.abs(observed-ref).max()))
    initial=AutoModel.from_pretrained('/models/prajjwal1--bert-tiny',config=BertConfig.from_json_file('/models/prajjwal1--bert-tiny/config.json'))
    changed=sum(not torch.equal(p.detach().cpu(),dict(initial.named_parameters())[name]) for name,p in model.named_parameters() if name in dict(initial.named_parameters()));assert changed>0
    proc=subprocess.run(['python','/artifacts/solution/main.py','encode','--checkpoint',str(cp),'--input','input/validation.jsonl','--output','evaluation/reloaded'],capture_output=True,text=True,timeout=90);assert proc.returncode==0,proc.stdout+proc.stderr
    for file in ['question_embeddings.npy','passage_embeddings.npy']:assert np.allclose(np.load(out/file),np.load(Path('evaluation/reloaded')/file),atol=1e-5)
    distinct=len(set(r['context'] for r in rows))
    qvec=np.load(out/'question_embeddings.npy');pvec=np.load(out/'passage_embeddings.npy');order=np.argsort(-(qvec@pvec.T),axis=1)
    def recall(k):return float(np.mean([any(rows[j]['context']==rows[i]['context'] for j in order[i,:k]) for i in range(len(rows))]))
    report.update(validation_queries=len(rows),unique_validation_contexts=distinct,changed_parameter_tensors=changed,max_reference_errors=errors,recall_at_1=recall(1),recall_at_5=recall(5),quality_limitation='The first source version contains one shared context; Recall is non-discriminating.' if distinct==1 else 'Tiny debug model and24passages; formal DPR/NQ retrieval quality is not asserted.')
    del model,initial;torch.cuda.empty_cache();command=['train','--input','input','--output','evaluation/profile_train','--epochs','1']
elif short=='F10':
    fields=np.load('input/train_fields.npy');pred=np.load(out/'rollout.npy');assert pred.shape==(3,5,32,32,64) and np.isfinite(pred).all()
    state=np.load(out/'state.npz');assert state['fields'].shape==(5,32,32,64) and np.allclose(state['fields'],pred[-1])
    cp=torch.load(out/'checkpoint.pt',map_location='cpu',weights_only=False);assert 'optimizer_state' in cp or 'optimizer' in cp
    assert any('weight' in k.lower() and (torch.is_complex(v) or (v.ndim>=5 and v.shape[-1]==2)) for k,v in cp['model_state'].items()),'no learned spectral weights (complex or real/imag pair storage)'
    mean=fields.mean(axis=(0,2,3,4));assert np.allclose(np.asarray(cp['normalization']['mean']),mean,rtol=1e-5,atol=1e-6)
    proc=subprocess.run(['python','/artifacts/solution/main.py','forecast','--checkpoint',str(out/'checkpoint.pt'),'--initial','input/validation_initial.npy','--steps','3','--output','evaluation/reloaded.npy'],capture_output=True,text=True,timeout=90);assert proc.returncode==0,proc.stdout+proc.stderr
    reloaded=np.load('evaluation/reloaded.npy');assert np.allclose(pred,reloaded,atol=1e-5,rtol=1e-5)
    gold=np.load('validation_labels.npy');assert gold.shape==pred.shape
    initial=np.load('input/validation_initial.npy');report.update(rollout_shape=list(pred.shape),hidden_rmse=float(np.sqrt(np.mean((pred-gold)**2))),persistence_rmse=float(np.sqrt(np.mean((initial[None]-gold)**2))),reload_error=float(np.abs(pred-reloaded).max()))
    command=['train','--input','input','--output','evaluation/profile_train','--steps','5']
else:raise ValueError(short)
sys.path.insert(0,'/artifacts/solution');sys.argv=['/artifacts/solution/main.py']+command
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
    try:runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
    except SystemExit as e:assert e.code in (0,None)
    torch.cuda.synchronize()
events=[e for e in prof.events() if e.device_type==torch.autograd.DeviceType.CUDA];assert len(events)>100
report.update(passed=True,cuda_kernel_events=len(events));Path('evaluation/results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
