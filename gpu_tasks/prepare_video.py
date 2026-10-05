"""Native VKITTI2 frames; masks/requests are explicit designer task inputs."""
import io,json,os,shutil,tarfile,zipfile
import numpy as np
from PIL import Image,ImageDraw
from assets import ROOT,ASSETS,digest,fetch
from prepare_graphs import manifest
from prepare_text import save,lock
from specify_ready import freeze
from remote_file import RemoteFile

def native_frames(kind,count=16):
    base='https://download.europe.naverlabs.com/virtual_kitti_2.0.3/';url=base+'vkitti_2.0.3_'+kind+'.tar'
    out=ASSETS/'vision/vkitti_debug'/kind;out.mkdir(parents=True,exist_ok=True)
    if len(list(out.glob('*')))>=count:return out
    chosen=[]
    with RemoteFile(url,block_size=1<<20,max_transfer=256*2**20) as remote:
        with tarfile.open(fileobj=remote,mode='r:') as archive:
            for member in archive:
                if not member.isfile() or '/Scene01/15-deg-left/' not in '/'+member.name or 'Camera_0' not in member.name:continue
                if not member.name.endswith(('.jpg','.png')):continue
                if member.size>8*2**20:raise ValueError('native single image exceeds budget')
                target=out/Path(member.name).name
                target.write_bytes(archive.extractfile(member).read());chosen.append({'member':member.name,'sha256':digest(target)})
                if len(chosen)==count:break
        transferred=remote.transferred
    assert len(chosen)==count
    (out.parent/(kind+'_source.json')).write_text(json.dumps({'url':url,'members':chosen,'bytes_transferred':transferred},indent=2))
    return out

def tasks():
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(native_frames,'rgb');b=pool.submit(native_frames,'depth');rgb=a.result();depth=b.result()
    files=sorted(rgb.glob('*.jpg'));depths=sorted(depth.glob('*.png'));assert len(files)==len(depths)==16
    tid='GPUv1-B10';p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True);(p/'images').mkdir(exist_ok=True);(p/'depth').mkdir(exist_ok=True)
    rows=[];gold=[]
    for i,(image,dep) in enumerate(zip(files,depths)):
        Image.open(image).convert('RGB').resize((392,126)).save(p/'images'/f'{i}.png')
        arr=np.asarray(Image.open(dep).resize((392,126),Image.Resampling.NEAREST)).astype(np.float32)/100
        if i<12:np.save(p/'depth'/f'{i}.npy',arr)
        else:gold.append(arr)
        rows.append({'id':str(i),'image':f'images/{i}.png','depth':f'depth/{i}.npy'})
    save(tid,'train.jsonl',rows[:12]);save(tid,'validation.jsonl',[{k:v for k,v in r.items() if k!='depth'} for r in rows[12:]])
    o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);np.save(o/'validation_labels.npy',np.stack(gold))
    lock(tid,'VKITTI2 Scene01/15-deg-left/Camera_0','depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf',{'depth_unit':'meters, nativeuint16centimeters/100','deviations':['same nativeVKITTI2 metricdepth family,12train/4heldoutadjacentframes instead offulltrain and KITTItest;392x126debug']})
    freeze(tid,'适配可重载的户外单目米制深度模型','''真实VKITTI2 RGB与对应米制depth，12train/4heldout，392×126。初始化 /models/depth-anything--Depth-Anything-V2-Metric-Outdoor-Small-hf，用AutoImageProcessor和AutoModelForDepthEstimation，CUDA微调至少12次更新、每train图进入一次；允许冻结backbone只训练depthhead；loss=valid像素(mean abs(predicted_depth-target_depth))，valid为0.1<depth<80米，预测双线性插值原图尺寸。保存标准HFcheckpoint、optimizer/step/RNG训练状态、predictions.npy(4,126,392)米制float32、run.json；入口 train --input input --output output，predict --checkpoint PATH --input validation.jsonl --output NPY新进程重载。独立检查真实metric head、标注参与梯度、有限权重更新和predictioncoverage、CUDAbackward、hiddenAbsRel/RMSE另报。''')
    tid='GPUv1-D06';p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True);(p/'frames').mkdir(exist_ok=True)
    for i,f in enumerate(files):Image.open(f).convert('RGB').resize((392,126)).save(p/'frames'/f'{i:05}.png')
    save(tid,'requests.jsonl',[{'id':'road-scene','frames':[f'frames/{i:05}.png' for i in range(0,16,2)],'fps':5,'questions':[{'id':'q1','text':'Describe the road scene and visible vehicles.'},{'id':'q2','text':'Describe how the viewpoint changes over this sequence.'},{'id':'q3','text':'Identify visible obstacles and road boundaries, avoiding details you cannot see.'}]}])
    lock(tid,'VKITTI2 authentic rendered driving sequence','Qwen/Qwen2.5-VL-3B-Instruct',{'deviations':['8sampledframes from16nativeVKITTI2 frames and3designerquestions rather thanVideoMME900videos/72Bmodel; noVideoMMEscoreclaimed']})
    freeze(tid,'为完整道路短片交付逐问题理解目录','''input/requests.jsonl包含完整16帧VKITTI2短片中均匀8帧及3个设计者问题。真实CUDA Qwen2.5-VL-3B-Instruct BF16 AutoProcessor把所有sampledframes作为有序多图上下文（允许实际video processor），不能只处理首帧，max_pixels每帧<=65536，greedy最多128新token每题。入口 run --input input --output output；输出 answers.jsonl包含videoID/questionID/answer/token_ids/used_frame_ids、run.json；infer --input JSONL --output DIR 支持新帧序列和新问题。独立检查8帧覆盖、3题覆盖、visionencoder真CUDA、fresh输入、生成重算；时间理解正确性人工/独立oracle另报，不能声称长视频VideoMME通过。''')
    tid='GPUv1-C06';p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True);(p/'frames').mkdir(exist_ok=True);(p/'masks').mkdir(exist_ok=True);o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);(o/'clean').mkdir(exist_ok=True)
    for i,f in enumerate(files):
        clean=Image.open(f).convert('RGB').resize((320,192));clean.save(o/'clean'/f'{i:05}.png')
        mask=Image.new('L',clean.size);ImageDraw.Draw(mask).rectangle((100+i,60,160+i,110),fill=255)
        damaged=clean.copy();damaged.paste((0,0,0),(0,0,320,192),mask);damaged.save(p/'frames'/f'{i:05}.png');mask.save(p/'masks'/f'{i:05}.png')
    source=ASSETS/'vision/propainter_source.zip'
    if not source.exists():raise ValueError('ProPainter source acquisition pending')
    (p/'upstream').mkdir(exist_ok=True)
    with zipfile.ZipFile(source) as z:
        prefix=z.namelist()[0].split('/')[0]+'/'
        for name in z.namelist():
            rel=Path(name[len(prefix):])
            if name.endswith('/') or not str(rel) or '..' in rel.parts or not name.endswith(('.py','.json','.txt','.md','.yml','.yaml')):continue
            target=p/'upstream'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
    required=['ProPainter.pth','raft-things.pth','recurrent_flow_completion.pth'];assert all((ASSETS/'models/ProPainter'/n).exists() for n in required)
    manifest(tid,{'source':'VKITTI2+sczhou/ProPainter official code and weights','frames':16,'resolution':[320,192],'code_zip_sha256':digest(source),'weights':{n:digest(ASSETS/'models/ProPainter'/n) for n in required},'deviations':['16genuineVKITTI2 drivingframeswithdesignerblackdamage/masks instead ofDAVIS480pcorpus; pretrainedProPainterunaltered; cleanreferenceprivate']})
    freeze(tid,'修复真实受损短片并交付完整视频','''input/frames有16帧真实VKITTI2短片的损坏图，input/masks指定需要修复的白区，干净图仅独立验证器可见。CUDA官方ProPainter，源码input/upstream，权重/models/ProPainter，复制源码到solution或output中的可写运行目录，用官方inference_propainter.py、--video input/frames --mask input/masks --width320 --height192 --fp16 --neighbor_length10 --ref_stride10 --subvideo_length16 --save_frames（参数按源--help校验）。权重挂载/链接到该代码weights路径以禁自动下载。入口 python solution/main.py run --input input --output output；交付repaired.mp4、frames/{index}.png、frame_manifest.json和run.json；新run可处理另一个帧/mask目录。保护区最终按mask与input composite，所有帧必须修复，不能复制上一帧/复制损坏输入或读干净图。独立检查帧数/顺序/尺寸/视频解码、保护区pixel一致、真实GPUflow与inpainting，mask区域PSNR/SSIM另报。''')

if __name__=='__main__':
    from pathlib import Path
    try:tasks();print('B10/D06/C06 READY',flush=True)
    except Exception as e:print('VIDEO_PREP_FAILED',repr(e),flush=True)
