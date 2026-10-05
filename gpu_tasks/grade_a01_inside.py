import json
from pathlib import Path
import subprocess
import torch
import numpy as np
from transformers import AutoModelForCausalLM,AutoTokenizer

Path('evaluation').mkdir(exist_ok=True)
out=Path('/artifacts/output');checkpoint=out/'checkpoint'
manifest=json.loads(Path('input/manifest.json').read_text())
reported=json.loads((out/'run.json').read_text())
rows=[json.loads(x) for x in Path('input/validation.jsonl').read_text().splitlines()]
responses=[json.loads(x) for x in (out/'responses.jsonl').read_text().splitlines()]
assert [x['id'] for x in rows]==[x['id'] for x in responses]
assert all(1<=len(x['generated_token_ids'])<=32 for x in responses)
tokenizer=AutoTokenizer.from_pretrained(checkpoint)
model=AutoModelForCausalLM.from_pretrained(checkpoint,dtype=torch.float32).eval().cuda()
def tokens(messages,generation=False):
    a=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=generation)
    if hasattr(a,'keys') and 'input_ids' in a:a=a['input_ids']
    return list(a)[:256]
with torch.inference_mode():
    losses=[]
    for row in rows:
        ids=torch.tensor([tokens(row['messages'])],device='cuda')
        losses.append(float(model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=ids).loss))
    for row,res in zip(rows[:3],responses[:3]):
        prefix=[]
        for message in row['messages']:
            if message['role']=='assistant':break
            prefix.append(message)
        ids=torch.tensor([tokens(prefix,True)],device='cuda')
        generated=model.generate(ids,attention_mask=torch.ones_like(ids),max_new_tokens=32,do_sample=False,pad_token_id=tokenizer.eos_token_id)[0,len(ids[0]):].tolist()
        assert generated==res['generated_token_ids'],(row['id'],generated,res['generated_token_ids'])
base=AutoModelForCausalLM.from_pretrained(manifest['model_container_path'],dtype=torch.float32)
changed=sum(not torch.equal(p.detach().cpu(),dict(base.named_parameters())[name]) for name,p in model.named_parameters())
assert changed>0
del base,model
torch.cuda.empty_cache()
state=torch.load(out/'training_state.pt',map_location='cpu',weights_only=False)
assert 'optimizer' in state and 'scheduler' in state and 'rng' in state
old_step=int(state['step']);assert old_step>0 and reported['train_examples']==64
del state
subprocess.run(['cp','-a',str(out),'/workspace/output'],check=True)
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as profiler:
    import runpy,sys
    sys.argv=['/artifacts/solution/main.py','train','--input','input','--output','output','--resume','output/training_state.pt','--steps','2']
    try:runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
    except SystemExit as e:assert e.code in (None,0)
    torch.cuda.synchronize()
new_state=torch.load('output/training_state.pt',map_location='cpu',weights_only=False)
assert new_state['step']==old_step+2
cuda=[e.name for e in profiler.events() if e.device_type==torch.autograd.DeviceType.CUDA]
assert any('gemm' in n.lower() or 'gemv' in n.lower() for n in cuda)
data={'passed':True,'validation_rows':len(rows),'mean_validation_nll':float(np.mean(losses)),'changed_parameter_tensors':changed,'generation_recomputed_rows':3,'resume_steps':[old_step,new_state['step']],'cuda_kernel_events':len(cuda),'reference_large_tested':False}
Path('evaluation/results.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps(data))
