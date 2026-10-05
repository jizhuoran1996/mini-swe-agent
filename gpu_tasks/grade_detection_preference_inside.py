"""Standard model recomputation; no delivered self-report is an oracle."""
import json,sys,runpy,subprocess
from pathlib import Path
import numpy as np
import torch
from PIL import Image

tid=sys.argv[1];kind=tid.split('-')[1];out=Path('/artifacts/output');Path('evaluation').mkdir(exist_ok=True)
report={'task_id':tid,'passed':False,'reference_large_tested':False}
if kind=='A02':
    from transformers import AutoModelForCausalLM,AutoTokenizer
    rows=[json.loads(x) for x in Path('input/validation.jsonl').read_text().splitlines()]
    p=json.loads((out/'preferences.json').read_text());pairs=p['pairs'];assert len(pairs)==len(rows)==8
    path='/models/HuggingFaceTB--SmolLM2-135M-Instruct';tok=AutoTokenizer.from_pretrained(path)
    policy=AutoModelForCausalLM.from_pretrained(out/'checkpoint',dtype=torch.float32).cuda().eval()
    ref=AutoModelForCausalLM.from_pretrained(path,dtype=torch.float32).cuda().eval()
    changed=sum(not torch.equal(v.cpu(),ref.state_dict()[k].cpu()) for k,v in policy.state_dict().items());assert changed>0
    state=torch.load(out/'training_state.pt',map_location='cpu',weights_only=False);assert any('optim' in k for k in state)
    # Response is the final assistant turn, never the duplicate user turn.
    def encode(row,key):
        prompt=[{'role':'user','content':row['prompt']}];response=[row[key][-1]];assert response[0]['role']=='assistant'
        a=tok.apply_chat_template(prompt,tokenize=False,add_generation_prompt=True);b=tok.apply_chat_template(prompt+response,tokenize=False,add_generation_prompt=False);assert b.startswith(a)
        left=tok(a,add_special_tokens=False)['input_ids'];right=tok(b[len(a):],add_special_tokens=False)['input_ids']
        if len(left)+len(right)>256:
            n=min(len(left),64) if len(right)>=256 else 256-len(right);left=left[-n:];right=right[:256-n]
        assert len(left)>0 and len(right)>0
        return torch.tensor([left+right],device='cuda'),len(left)
    def score(m,x,start):
        with torch.no_grad():logits=m(x).logits[0,start-1:-1].float();return float(logits.log_softmax(-1).gather(1,x[0,start:,None]).sum())
    margins=[];errors=[]
    for row,pair in zip(rows,pairs):
        assert str(pair['id'])==str(row['id'])
        vals=[]
        for name,m in [('policy',policy),('reference',ref)]:
            for key in ['chosen','rejected']:
                x,start=encode(row,key);v=score(m,x,start);errors.append(abs(v-pair[name][key+'_logprob']));assert np.isclose(v,pair[name][key+'_logprob'],atol=.02,rtol=1e-5);vals.append(v)
        margin=.1*((vals[0]-vals[1])-(vals[2]-vals[3]));assert np.isclose(margin,pair['margin'],atol=.005);assert np.isclose(np.logaddexp(0,-margin),pair['dpo_loss'],atol=.005);margins.append(margin)
    report.update(validation_pairs=8,changed_parameter_tensors=changed,max_logprob_error=max(errors),preference_accuracy=float(np.mean(np.asarray(margins)>0)))
    del policy,ref;torch.cuda.empty_cache();command=['train','--input','input','--output','evaluation/profile_training','--epochs','1']
else:
    from torchvision.models.detection import retinanet_resnet50_fpn,maskrcnn_resnet50_fpn
    from torchvision.transforms.functional import to_tensor
    images=json.loads(Path('input/images.json').read_text());errors=[];total=0
    if kind=='B02':
        bind=json.loads(Path('/models/torchvision/retinanet.json').read_text());model=retinanet_resnet50_fpn(weights=None,weights_backbone=None,num_classes=91,min_size=320,max_size=640)
        model.load_state_dict(torch.load(bind['container_path'],map_location='cpu',weights_only=True),strict=True);pred=json.loads((out/'detections.json').read_text())['detections'];command=['detect','--input','input','--output','evaluation/profile_inference']
    else:
        from pycocotools import mask as mask_api
        import cv2
        checkpoint=torch.load(out/'checkpoint.pt',map_location='cpu',weights_only=False);assert checkpoint['step']>=12 and checkpoint['optimizer_state_dict']['state']
        initial=torch.load('/models/torchvision/maskrcnn_resnet50_fpn_coco-bf2d0c1e.pth',map_location='cpu',weights_only=True)
        changed=sum(not torch.equal(v,initial[k]) for k,v in checkpoint['model_state_dict'].items() if k in initial);assert changed>0
        model=maskrcnn_resnet50_fpn(weights=None,weights_backbone=None,num_classes=91,min_size=320,max_size=640);model.load_state_dict(checkpoint['model_state_dict'],strict=True)
        pred=json.loads((out/'reloaded/instances.json').read_text())['images'];contours=json.loads((out/'reloaded/contours.json').read_text())['images'];assert len(contours)==len(images)
        report.update(changed_parameter_tensors=changed,optimizer_steps=checkpoint['step']);command=['train','--input','input','--output','evaluation/profile_training']
    assert len(pred)==len(images)==16;model=model.cuda().eval()
    for index,(meta,record) in enumerate(zip(images,pred)):
        assert record['image_id']==meta['id'];im=Image.open(Path('input/images')/meta['file_name']).convert('RGB')
        with torch.no_grad():ref=model([to_tensor(im).cuda()])[0]
        keep=ref['scores']>=.25;boxes=ref['boxes'][keep].cpu().numpy();labels=ref['labels'][keep].cpu().numpy();scores=ref['scores'][keep].cpu().numpy();total+=len(scores)
        if kind=='B02':
            assert record['original_size']==list(im.size);assert np.array_equal(record['labels'],labels);assert np.allclose(np.asarray(record['boxes']).reshape(-1,4),boxes,atol=.05);assert np.allclose(record['scores'],scores,atol=1e-4)
        else:
            instances=record['instances'];assert len(instances)==len(scores);masks=(ref['masks'][keep,0]>.5).cpu().numpy()
            for j,(inst,binary) in enumerate(zip(instances,masks)):
                assert inst['category_id']==labels[j] and np.isclose(inst['score'],scores[j],atol=1e-4);assert np.allclose(inst['box_xyxy'],boxes[j],atol=.05)
                rle=inst['segmentation'];rle={'size':rle['size'],'counts':rle['counts'].encode()};decoded=mask_api.decode(rle);assert decoded.shape==binary.shape and np.array_equal(decoded,binary)
                expected,_=cv2.findContours(binary.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE);actual=[x['contour'] for x in contours[index]['contours'] if x['instance_index']==j]
                expected=[x.reshape(-1,2).tolist() for x in expected if len(x)>=3 and cv2.contourArea(x)>=1.0];assert sorted(map(str,actual))==sorted(map(str,expected))
    assert total>0;report.update(images=16,instances=total,standard_checkpoint_recomputation=True)
    if kind=='B02':
        p=subprocess.run(['python','/artifacts/solution/main.py','query','--catalog',str(out/'catalog.json'),'--image-id',str(images[0]['id'])],capture_output=True,text=True,timeout=30);assert p.returncode==0;reply=json.loads(p.stdout);assert reply['image_id']==images[0]['id']
    del model;torch.cuda.empty_cache()
sys.path.insert(0,'/artifacts/solution');sys.argv=['/artifacts/solution/main.py']+command
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
    try:runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
    except SystemExit as e:assert e.code in (0,None)
    torch.cuda.synchronize()
events=[e for e in prof.events() if e.device_type==torch.autograd.DeviceType.CUDA];assert len(events)>10
report.update(passed=True,cuda_kernel_events=len(events));Path('evaluation/results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
