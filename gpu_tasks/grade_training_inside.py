"""Independent artifact, held-out metric, reload and actual CUDA checks."""
import json,runpy,subprocess,sys
from pathlib import Path
import numpy as np
import torch
from sklearn.metrics import roc_auc_score

tid=sys.argv[1];kind=tid.split('-')[1];out=Path('/artifacts/output');Path('evaluation').mkdir(exist_ok=True)
report={'task_id':tid,'passed':False,'reference_large_tested':False}
def execute(args):
    p=subprocess.run(['python','/artifacts/solution/main.py']+args,capture_output=True,text=True,timeout=120)
    assert p.returncode==0,p.stdout+p.stderr
def profile(args):
    sys.path.insert(0,'/artifacts/solution');sys.argv=['/artifacts/solution/main.py']+args
    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
        try:runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
        except SystemExit as e:assert e.code in (0,None)
        torch.cuda.synchronize()
    events=[e for e in prof.events() if e.device_type==torch.autograd.DeviceType.CUDA]
    assert len(events)>30,len(events)
    report['cuda_kernel_events']=len(events)
if kind in ['A07','B01','F01','F02']:
    checkpoint=out/'checkpoint.pt';state=torch.load(checkpoint,map_location='cpu',weights_only=False)
    assert any('optim' in k for k in state),state.keys()
    optim=next(v for k,v in state.items() if 'optim' in k and isinstance(v,dict) and 'state' in v)
    assert len(optim['state'])>0,'optimizer has no actual update state'
    assert any(float(v.get('step',0))>0 for v in optim['state'].values())
    if kind=='A07':
        p=np.load(out/'validation_predictions.npy');gold=np.load('validation_labels.npy');assert p.shape==gold.shape and ((p>=0)&(p<=1)).all() and np.isfinite(p).all()
        params=state['model_state_dict'];emb=[v for k,v in params.items() if 'embedding' in k and k.endswith('weight')];assert len(emb)==26 and all(v.shape[1]==8 for v in emb)
        report.update(heldout_auc=float(roc_auc_score(gold,p)),embedding_tables=len(emb),validation_rows=len(p))
        command=['predict','--checkpoint',str(checkpoint),'--input','input/validation.jsonl','--output','evaluation/reloaded.npy'];execute(command);q=np.load('evaluation/reloaded.npy');assert np.allclose(p,q,atol=1e-6)
        rows=[json.loads(x) for x in Path('input/train.jsonl').read_text().splitlines()][:3];Path('new.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        command=['predict','--checkpoint',str(checkpoint),'--input','new.jsonl','--output','evaluation/new.npy'];execute(command);assert np.load('evaluation/new.npy').shape==(3,)
    elif kind=='B01':
        from torchvision.models import resnet50
        from torchvision.transforms import functional as TF
        model=resnet50(weights=None);model.fc=torch.nn.Linear(model.fc.in_features,10);model.load_state_dict(state['state_dict']);model.cuda().eval()
        x=np.load('input/validation_images.npy');p=np.load(out/'validation_predictions.npy');y=np.load('validation_labels.npy');assert p.shape==(len(x),10) and np.allclose(p.sum(1),1,atol=1e-5)
        predictions=[]
        with torch.no_grad():
            bs=int(state['batch_size'])
            for lo in range(0,len(x),bs):
                images=torch.from_numpy(x[lo:lo+bs]).cuda().float().div_(255).permute(0,3,1,2).contiguous()
                images=torch.nn.functional.interpolate(images,size=(224,224),mode='bilinear',align_corners=False,antialias=True);images=TF.normalize(images,[.485,.456,.406],[.229,.224,.225]);predictions.append(model(images).softmax(1).cpu().numpy())
        ref=np.concatenate(predictions);assert np.allclose(ref,p,atol=1e-4,rtol=1e-4),float(np.abs(ref-p).max())
        report.update(heldout_accuracy=float(np.mean(p.argmax(1)==y)),max_reference_error=float(np.abs(ref-p).max()))
        new_images=torch.from_numpy(x[[3,17,81]]).cuda().float().div_(255).permute(0,3,1,2).contiguous()
        new_images=torch.nn.functional.interpolate(new_images,size=(224,224),mode='bilinear',align_corners=False,antialias=True)
        with torch.no_grad():new_reference=model(TF.normalize(new_images,[.485,.456,.406],[.229,.224,.225])).softmax(1).cpu().numpy()
        del model,new_images;torch.cuda.empty_cache();np.save('new.npy',x[[3,17,81]])
        command=['predict','--checkpoint',str(checkpoint),'--input','new.npy','--output','evaluation/new.npy'];execute(command);assert np.allclose(np.load('evaluation/new.npy'),new_reference,atol=1e-4)
    elif kind=='F01':
        x=np.load('input/validation_fields.npy');p=np.load(out/'validation_predictions.npy');y=np.load('validation_labels.npy');assert p.shape==(len(x),4) and np.isfinite(p).all()
        report.update(hidden_mse=float(np.square(p-y).mean()),validation_volumes=len(x))
        command=['predict','--checkpoint',str(checkpoint),'--input','input/validation_fields.npy','--output','evaluation/reloaded.npy'];execute(command);assert np.allclose(np.load('evaluation/reloaded.npy'),p,atol=1e-5)
        np.save('new.npy',np.load('input/train_fields.npy')[[0]]);command=['predict','--checkpoint',str(checkpoint),'--input','new.npy','--output','evaluation/new.npy'];execute(command);assert np.load('evaluation/new.npy').shape==(1,4)
    else:
        x=np.load('input/validation_fields.npy');p=np.load(out/'predictions.npy');probs=np.load(out/'probabilities.npy');y=np.load('validation_labels.npy');assert p.shape==y.shape and probs.shape==(len(x),3,192,288)
        assert np.allclose(probs.sum(1),1,atol=1e-5) and np.array_equal(p,probs.argmax(1)) and np.isfinite(probs).all()
        ious=[]
        for c in range(3):
            union=((p==c)|(y==c)).sum();ious.append(float(((p==c)&(y==c)).sum()/union) if union else None)
        report.update(hidden_class_iou=ious,validation_fields=len(x))
        command=['predict','--checkpoint',str(checkpoint),'--input','input/validation_fields.npy','--output','evaluation/reloaded'];execute(command);assert np.array_equal(np.load('evaluation/reloaded/predictions.npy'),p)
        np.save('new.npy',np.load('input/train_fields.npy')[:1]);command=['predict','--checkpoint',str(checkpoint),'--input','new.npy','--output','evaluation/new'];execute(command);assert np.load('evaluation/new/predictions.npy').shape==(1,192,288)
    del state,optim;torch.cuda.empty_cache();profile(command)
elif kind in ['B04','B10']:
    from transformers import AutoTokenizer,AutoImageProcessor,AutoModelForSemanticSegmentation,AutoModelForDepthEstimation
    from PIL import Image
    base='/models/'+('nvidia--segformer-b0-finetuned-cityscapes-1024-1024' if kind=='B04' else 'depth-anything--Depth-Anything-V2-Metric-Outdoor-Small-hf')
    cls=AutoModelForSemanticSegmentation if kind=='B04' else AutoModelForDepthEstimation
    model=cls.from_pretrained(out/'checkpoint').cuda().eval();initial=cls.from_pretrained(base)
    originals=dict(initial.named_parameters());changed=sum(not torch.equal(v.detach().cpu(),originals[k]) for k,v in model.named_parameters() if k in originals);assert changed>0
    p=np.load(out/'predictions.npy');gold=np.load('validation_labels.npy');assert p.shape==gold.shape and np.isfinite(p).all()
    rows=[json.loads(x) for x in Path('input/validation.jsonl').read_text().splitlines()]
    if kind=='B04':
        assert ((p>=0)&(p<19)).all();ious=[]
        for c in range(19):
            live=gold!=255;inter=((p==c)&(gold==c)&live).sum();union=(((p==c)|(gold==c))&live).sum();ious.append(float(inter/union) if union else None)
        report['hidden_class_iou']=ious
    else:
        valid=(gold>.1)&(gold<80);assert (p>=0).all();report.update(hidden_absrel=float((np.abs(p-gold)[valid]/gold[valid]).mean()),hidden_rmse=float(np.sqrt(np.square(p-gold)[valid].mean())))
    del model,initial;torch.cuda.empty_cache();command=['predict','--checkpoint',str(out/'checkpoint'),'--input','input/validation.jsonl','--output','evaluation/reloaded.npy'];execute(command);q=np.load('evaluation/reloaded.npy');assert np.allclose(p,q,atol=1e-4,rtol=1e-5)
    report.update(changed_parameter_tensors=changed,reload_error=float(np.abs(p-q).max()),validation_images=len(rows));profile(command)
elif kind in ['A04','A06']:
    from transformers import WhisperForConditionalGeneration,Wav2Vec2ForPreTraining
    cls=WhisperForConditionalGeneration if kind=='A04' else Wav2Vec2ForPreTraining
    base='/models/'+('openai--whisper-tiny' if kind=='A04' else 'facebook--wav2vec2-base')
    model=cls.from_pretrained(out/'checkpoint');initial=cls.from_pretrained(base);originals=dict(initial.named_parameters());changed=sum(not torch.equal(v.detach(),originals[k]) for k,v in model.named_parameters() if k in originals);assert changed>0
    state=torch.load(out/'training_state.pt',map_location='cpu',weights_only=False);assert any('optim' in k for k in state);del model,initial,state
    rows=[json.loads(x) for x in Path('input/validation.jsonl').read_text().splitlines()]
    if kind=='A04':
        records=[json.loads(x) for x in (out/'transcripts.jsonl').read_text().splitlines()];assert [r['id'] for r in records]==[r['id'] for r in rows] and all(r['text'].strip() and r['token_ids'] for r in records)
        command=['transcribe','--checkpoint',str(out/'checkpoint'),'--input','input/validation.jsonl','--output','evaluation/reloaded.jsonl'];execute(command);q=[json.loads(x) for x in Path('evaluation/reloaded.jsonl').read_text().splitlines()];assert [r['token_ids'] for r in q]==[r['token_ids'] for r in records]
    else:
        p=np.load(out/'reloaded/features.npy');assert p.shape==(8,768) and np.isfinite(p).all() and np.allclose(np.linalg.norm(p,axis=1),1,atol=1e-5)
        command=['encode','--checkpoint',str(out/'checkpoint'),'--input','input/validation.jsonl','--output','evaluation/reloaded'];execute(command);assert np.allclose(np.load('evaluation/reloaded/features.npy'),p,atol=1e-5)
    report.update(changed_parameter_tensors=changed,validation_recordings=len(rows));profile(command)
else:raise ValueError(kind)
report['passed']=True;Path('evaluation/results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
