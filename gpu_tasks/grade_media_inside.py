"""Decode full media; frozen model replay and genuine new requests."""
import sys,json,subprocess,runpy,shutil,gc,math
from pathlib import Path
import numpy as np
import torch
from PIL import Image
import soundfile as sf

tid=sys.argv[1];kind=tid.split('-')[1];out=Path('/artifacts/output');Path('evaluation').mkdir(exist_ok=True)
report={'task_id':tid,'passed':False,'reference_large_tested':False,'content_quality_verified':False}
def jsonl(p):return [json.loads(x) for x in p.read_text().splitlines()]
if kind not in ['C06','C10']:
    requests=jsonl(Path('input/requests.jsonl'));index=jsonl(out/'index.jsonl');assert len(index)==len(requests);assert [str(r.get('id',r.get('request_id'))) for r in index]==[str(r['id']) for r in requests];report['requests']=len(index)
if kind in ['C01','C02','C03']:
    for rec,req in zip(index,requests):
        image=Image.open(out/rec.get('image',rec.get('output'))).convert('RGB');a=np.asarray(image);assert image.size==((256,256) if kind=='C01' else (512,512)) and a.std()>1
        if kind=='C02':
            src=np.asarray(Image.open(Path('input')/req['image']).convert('RGB'));mask=np.asarray(Image.open(Path('input')/req['mask']).convert('L'))>0;assert np.array_equal(a[~mask],src[~mask]);assert not np.array_equal(a[mask],src[mask])
        if kind=='C03':
            import cv2
            im=Image.open(Path('input')/req['image']).convert('RGB').resize((512,512));edges=cv2.Canny(np.asarray(im.convert('L')),100,200);control=np.asarray(Image.open(out/rec['control']));assert np.array_equal(control[:,:,0],edges)
    from diffusers import StableDiffusionPipeline,StableDiffusionInpaintPipeline,StableDiffusionControlNetPipeline,ControlNetModel
    req=requests[0];rec=index[0];seed=int(rec['seed']);gen=torch.Generator(device='cpu' if kind=='C03' else 'cuda').manual_seed(seed)
    if kind=='C01':pipe=StableDiffusionPipeline.from_pretrained('/models/segmind--tiny-sd',torch_dtype=torch.float16,safety_checker=None,requires_safety_checker=False).to('cuda');kwargs={}
    elif kind=='C02':
        pipe=StableDiffusionInpaintPipeline.from_pretrained('/models/stable-diffusion-v1-5--stable-diffusion-inpainting',torch_dtype=torch.float16).to('cuda');im=Image.open(Path('input')/req['image']).convert('RGB');mask=Image.open(Path('input')/req['mask']).convert('L');kwargs={'image':im,'mask_image':mask}
    else:
        controlnet=ControlNetModel.from_pretrained('/models/lllyasviel--sd-controlnet-canny',torch_dtype=torch.float16);pipe=StableDiffusionControlNetPipeline.from_pretrained('/models/stable-diffusion-v1-5--stable-diffusion-v1-5',controlnet=controlnet,torch_dtype=torch.float16,safety_checker=None,requires_safety_checker=False).to('cuda');pipe.enable_attention_slicing();kwargs={'image':Image.open(out/rec['control']),'controlnet_conditioning_scale':1.0}
    pipe.set_progress_bar_config(disable=True);size=256 if kind=='C01' else 512
    with torch.inference_mode():ref=pipe(rec['prompt'],height=size,width=size,num_inference_steps=12,guidance_scale=7.5,generator=gen,**kwargs).images[0]
    if kind=='C02':ref=Image.composite(ref,im,mask)
    actual=np.asarray(Image.open(out/rec.get('image',rec.get('output'))).convert('RGB'));error=float(np.abs(actual.astype(float)-np.asarray(ref,dtype=float)).mean());assert error<=2,error;report['seed_replay_mean_pixel_error']=error
    del pipe;gc.collect();torch.cuda.empty_cache()
elif kind in ['C04','C05']:
    total=0;temporal=[]
    for rec in index:
        video=out/rec['video'];probe=subprocess.run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=nb_read_frames,width,height,r_frame_rate','-of','json',str(video)],capture_output=True,text=True,check=True);meta=json.loads(probe.stdout)['streams'][0];n=16 if kind=='C04' else 14;assert int(meta['nb_read_frames'])==n and meta['width']==meta['height']==256
        frames=sorted((out/rec['frames_dir']).glob('*.png'));assert len(frames)==n;stack=np.stack([np.asarray(Image.open(f).convert('RGB')) for f in frames]);assert stack.std()>2 and not np.array_equal(stack[0],stack[-1]);temporal.append(float(stack.astype(float).std(0).mean()));total+=n
    report.update(frames=total,temporal_pixel_std=temporal)
elif kind in ['C07','C08','C09']:
    durations=[]
    for rec in index:
        path=out/rec.get('wav',rec.get('audio_path'));audio,sr=sf.read(path);assert audio.ndim==1 and np.isfinite(audio).all() and np.sqrt(np.mean(audio**2))>1e-5;assert sr=={'C07':32000,'C08':16000,'C09':24000}[kind];duration=len(audio)/sr;assert duration>.1
        if kind!='C09':assert abs(duration-4)<.2
        durations.append(duration)
    report.update(sample_rate=sr,durations_s=durations,all_non_silent=True)
    # Standard API reproduces one independently decoded waveform, not an agent metric.
    if kind=='C07':
        from transformers import AutoProcessor,MusicgenForConditionalGeneration
        torch.backends.cudnn.enabled=False
        path='/models/facebook--musicgen-small';proc=AutoProcessor.from_pretrained(path);model=MusicgenForConditionalGeneration.from_pretrained(path).to('cuda').eval();batch=proc(text=[requests[0]['prompt']],padding=True,return_tensors='pt').to('cuda')
        with torch.no_grad():ref=model.generate(**batch,max_new_tokens=200,do_sample=False)[0,0].cpu().numpy()
        actual,_=sf.read(out/index[0]['wav']);assert actual.shape==ref.shape;error=float(np.abs(actual-ref).mean());assert error<.001,error;report['waveform_mean_absolute_error']=error;del model;gc.collect();torch.cuda.empty_cache()
    if kind=='C08':
        from diffusers import AudioLDMPipeline
        pipe=AudioLDMPipeline.from_pretrained('/models/cvssp--audioldm-s-full-v2',torch_dtype=torch.float16).to('cuda');pipe.set_progress_bar_config(disable=True)
        with torch.no_grad():ref=pipe(requests[0]['prompt'],audio_length_in_s=4,num_inference_steps=12,guidance_scale=2.5,num_waveforms_per_prompt=1,generator=torch.Generator(device='cuda').manual_seed(int(index[0]['seed'])),output_type='np').audios[0]
        actual,_=sf.read(out/index[0]['audio_path']);assert actual.shape==ref.shape;error=float(np.abs(actual-ref).mean());assert error<.002,error;report['waveform_mean_absolute_error']=error;del pipe;gc.collect();torch.cuda.empty_cache()
    if kind=='C09':report['quality_limitation']='Non-silence, sample rate, clone API and CUDA replay checked; speech accuracy and speaker similarity are not scored.'
elif kind=='C06':
    images=sorted((out/'frames').glob('*.png'));inputs=sorted(Path('input/frames').glob('*.png'));masks=sorted(Path('input/masks').glob('*.png'));assert len(images)==len(inputs)==len(masks)==16;mses=[]
    for a,b,c in zip(images,inputs,masks):
        result=np.asarray(Image.open(a).convert('RGB'));src=np.asarray(Image.open(b).convert('RGB'));mask=np.asarray(Image.open(c).convert('L'))>0;assert result.shape==(192,320,3) and np.array_equal(result[~mask],src[~mask]) and not np.array_equal(result[mask],src[mask]);clean=np.asarray(Image.open(Path('clean')/b.name).convert('RGB'));mses.append(np.square(result[mask].astype(float)-clean[mask]).mean())
    probe=subprocess.run(['ffprobe','-v','error','-count_frames','-show_entries','stream=nb_read_frames','-of','json',str(out/'repaired.mp4')],capture_output=True,text=True,check=True);assert int(json.loads(probe.stdout)['streams'][0]['nb_read_frames'])==16
    report.update(frames=16,masked_psnr_db=float(10*np.log10(255**2/np.mean(mses))),protected_pixels_exact=True)
elif kind=='C10':
    import trimesh
    obj=trimesh.load(out/'asset.glb',force='mesh');assert len(obj.vertices)>100 and len(obj.faces)>100 and np.isfinite(obj.vertices).all() and (obj.area_faces>0).all();assert obj.faces.max()<len(obj.vertices);# Decode the standard GLB accessor independently; force='mesh' may discard texture vertex_attributes.
    import struct
    blob=(out/'asset.glb').read_bytes();length=struct.unpack_from('<I',blob,12)[0];doc=json.loads(blob[20:20+length]);assert 'COLOR_0' in doc['meshes'][0]['primitives'][0]['attributes'];material=doc['materials'][0]['pbrMetallicRoughness'];assert material['metallicFactor']==0 and material['roughnessFactor']==.5
    attribute=doc['meshes'][0]['primitives'][0]['attributes']['COLOR_0'];accessor=doc['accessors'][attribute];view=doc['bufferViews'][accessor['bufferView']];dtype=np.dtype({5121:'u1',5123:'<u2',5126:'<f4'}[accessor['componentType']]);components={'VEC3':3,'VEC4':4}[accessor['type']];offset=20+length+8+view.get('byteOffset',0)+accessor.get('byteOffset',0);colors=np.ndarray((accessor['count'],components),dtype=dtype,buffer=blob,offset=offset,strides=(view.get('byteStride',components*dtype.itemsize),dtype.itemsize));assert len(colors)==len(obj.vertices) and np.isfinite(colors).all() and np.ptp(colors[:,:3])>0
    assert (out/'mesh.ply').exists();assert len(list(out.rglob('*.png')))>=3;report.update(vertices=len(obj.vertices),faces=len(obj.faces),bounds=obj.bounds.tolist(),quality_limitation='Geometry is decodable; learned PBR materials and perceptual reconstruction quality are not asserted.')
else:raise ValueError(kind)
# Re-run a real new request through the delivered entry point under CUPTI.
source=Path('/artifacts/solution/main.py');sys.path.insert(0,str(source.parent))
if kind not in ['C06','C10']:
    target=Path('evaluation/new_input');shutil.copytree('input',target);new=dict(requests[0]);new['id']='new_media_call'
    if kind in ['C01','C04','C07','C08']:new['prompt']='A gentle breeze through a quiet forest' if kind in ['C07','C08'] else 'A red boat beside a peaceful lake';new['text']=new['prompt']
    if kind=='C09':new['text']='This recording is a new request for the library.';new['prompt']=new['text']
    new['seed']=7319;(target/'requests.jsonl').write_text(json.dumps(new)+'\n')
    if (target/'manifest.json').exists():
        import hashlib
        manifest=json.loads((target/'manifest.json').read_text());manifest.setdefault('files',{})['requests.jsonl']=hashlib.sha256((target/'requests.jsonl').read_bytes()).hexdigest();(target/'manifest.json').write_text(json.dumps(manifest))
    command=['run','--input',str(target),'--output','evaluation/new_output']
else:command=['run','--input','input','--output','evaluation/new_output']
if kind=='C06':
    # Its official CLI runs in a child. Profile that pinned upstream directly in
    # this interpreter, then compare its restored pixels with delivered frames.
    source=Path('input/upstream/inference_propainter.py');work=Path('evaluation/upstream');shutil.copytree('input/upstream',work);(work/'weights').mkdir(exist_ok=True)
    Path('weights').mkdir(exist_ok=True)
    for w in Path('/models/ProPainter').glob('*.pth'):
        (work/'weights'/w.name).symlink_to(w);(Path('weights')/w.name).symlink_to(w)
    source=work/'inference_propainter.py';sys.path.insert(0,str(work.resolve()));command=['--video','input/frames','--mask','input/masks','--width','320','--height','192','--fp16','--neighbor_length','10','--ref_stride','10','--subvideo_length','16','--save_frames','--output','evaluation/official_reference']
sys.argv=[str(source)]+command
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
    try:runpy.run_path(str(source),run_name='__main__')
    except SystemExit as e:assert e.code in (None,0)
    torch.cuda.synchronize()
events=[e for e in prof.events() if e.device_type==torch.autograd.DeviceType.CUDA];assert len(events)>10
if kind=='C06':
    ref_frames=sorted(Path('evaluation/official_reference').rglob('*.png'));ref_frames=[p for p in ref_frames if p.parent.name=='frames'];assert len(ref_frames)==16
    for got,ref,mask in zip(images,ref_frames,masks):
        m=np.asarray(Image.open(mask).convert('L'))>0;a=np.asarray(Image.open(got).convert('RGB'));b=np.asarray(Image.open(ref).convert('RGB'));assert np.abs(a[m].astype(float)-b[m]).mean()<2
else:
    assert (Path('evaluation/new_output')/'run.json').exists()
    if kind=='C10':
        p=subprocess.run(['python','/artifacts/solution/main.py','inspect','--asset',str(out/'asset.glb'),'--output','evaluation/reloaded.json'],capture_output=True,text=True,timeout=30);assert p.returncode==0,p.stdout+p.stderr
    else:
        fresh=jsonl(Path('evaluation/new_output/index.jsonl'));assert len(fresh)==1 and fresh[0].get('id',fresh[0].get('request_id'))=='new_media_call'
report.update(passed=True,cuda_kernel_events=len(events),fresh_process_or_request=True);Path('evaluation/results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
