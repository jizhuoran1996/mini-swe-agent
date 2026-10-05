"""Acquire small native NERSC CosmoFlow and CAM5 samples with hard budgets."""
import gzip,io,json,re,struct,tarfile
import numpy as np
import h5py,requests
from assets import ROOT,ASSETS,fetch,digest
from prepare_graphs import manifest
from specify_ready import freeze
from remote_file import RemoteFile

def wire(buf):
    pos=0
    def varint():
        nonlocal pos
        value=0;shift=0
        while True:
            byte=buf[pos];pos+=1;value|=(byte&127)<<shift
            if byte<128:return value
            shift+=7
    fields=[]
    while pos<len(buf):
        tag=varint();kind=tag&7
        if kind==2:
            size=varint();value=buf[pos:pos+size];pos+=size
        elif kind==5:value=buf[pos:pos+4];pos+=4
        elif kind==1:value=buf[pos:pos+8];pos+=8
        elif kind==0:value=varint()
        else:raise ValueError('unsupported source protobuf wire type')
        fields.append((tag>>3,value))
    return fields

def cosmos():
    tid='GPUv1-F01';p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True)
    url='https://portal.nersc.gov/project/dasrepo/cosmoflow-benchmark/cosmoUniverse_2019_05_4parE_tf_v2_mini.tar'
    chosen={'train':[],'validation':[]};sources=[]
    with RemoteFile(url,block_size=65536,max_transfer=512*2**20) as remote:
        with tarfile.open(fileobj=remote,mode='r:') as archive:
            for index,item in enumerate(archive):
                if index>5000:raise ValueError('mini archive split search budget exceeded')
                split='validation' if any(s in item.name.split('/') for s in ['val','validation']) else 'train' if 'train' in item.name.split('/') else None
                target=4 if split=='train' else 2
                if not item.isfile() or not item.name.endswith(('.tfrecord','.tfrecord.gz')) or split is None or len(chosen[split])>=target:continue
                if item.size>32*2**20:raise ValueError('unexpected native record size')
                buf=archive.extractfile(item).read()
                if buf.startswith(b'\x1f\x8b'):buf=gzip.decompress(buf)
                length=struct.unpack('<Q',buf[:8])[0];example=buf[12:12+length]
                features={}
                for _,entry in wire(wire(example)[0][1]):
                    fields=wire(entry);key=fields[0][1].decode();feature=wire(fields[1][1]);list_field=feature[0][1];values=wire(list_field)
                    features[key]=values[0][1]
                x=np.frombuffer(features['x'],dtype=np.int16).reshape(128,128,128,4).copy();y=np.frombuffer(features['y'],dtype='<f4').copy()
                assert y.shape==(4,) and np.isfinite(y).all()
                chosen[split].append((x,y));sources.append({'member':item.name,'bytes':item.size})
                print('COSMO_NATIVE',split,len(chosen[split]),x.shape,y.tolist(),flush=True)
                if len(chosen['train'])==4 and len(chosen['validation'])==2:break
        transferred=remote.transferred
    assert all(chosen.values())
    np.save(p/'train_fields.npy',np.stack([x for x,y in chosen['train']]));np.save(p/'train_targets.npy',np.stack([y for x,y in chosen['train']]))
    np.save(p/'validation_fields.npy',np.stack([x for x,y in chosen['validation']]))
    o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);np.save(o/'validation_labels.npy',np.stack([y for x,y in chosen['validation']]))
    manifest(tid,{'source':url,'source_members':sources,'bytes_transferred':transferred,'deviations':['fourtrain/twoval genuine native128cubed4channel TFv2 mini samples; PyTorch small3DCNN instead ofdistributedTensorFlowfullCosmoFlow; notformalquality']})
    freeze(tid,'从真实宇宙模拟体数据训练可重载参数估计器','''input/train_fields.npy为4个真正CosmoFlow TFv2 128×128×128×4 int16粒子数裁块，train_targets.npy为对应4个归一化宇宙参数；validation_fields.npy两个源val裁块无label。CUDA真实3DCNN：先log1p(max(count,0))，各样本除自身均值（零时1），卷积/池化编码3D全部四个redshift通道，回归4参数，MSE，至少5优化器更新且所有train样本覆盖；每参数输出限制[-1,1]或记录未限制。入口 python solution/main.py train --input input --output output；保存checkpoint.pt含模型config/参数/optimizer/step/RNG，validation_predictions.npy(2,4)、run.json；predict --checkpoint PATH --input NPY --output NPY支持新体数据。独立检查source标签绑定、真实CUDA3Dforward/backward、checkpoint变化、重载预测和隐藏MSE报告，不要求4样本收敛到正式MAE阈值。''')

def cam():
    tid='GPUv1-F02';p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True)
    base='https://portal.nersc.gov/project/dasrepo/deepcam/climate-data/All-Hist/'
    splitnames={'train':['data-1996-01-01-00-3.h5','data-1996-01-01-00-5.h5','data-1996-01-01-01-1.h5','data-1996-01-01-01-3.h5','data-1996-01-01-01-5.h5','data-1996-01-01-02-1.h5'],'validation':['data-1996-01-01-00-1.h5','data-1996-01-02-00-3.h5']}
    for split,count in [('train',6),('validation',2)]:
        if split in splitnames:continue
        with requests.get(base+split+'/',stream=True,timeout=30) as response:
            response.raise_for_status();buf=b''
            for block in response.iter_content(65536):
                buf+=block
                if len(buf)>=256*1024:break
        names=re.findall('href="([^"<>]+\.h5)"',buf.decode());assert len(names)>=count;splitnames[split]=names[:count]
    sources=[];fields={};labels={}
    for split,names in splitnames.items():
        xs=[];ys=[]
        for name in names:
            file=fetch(base+split+'/'+name,ASSETS/'science/deepcam'/split/name,max_bytes=96*2**20)
            with h5py.File(file,'r') as h:
                group=h['climate'] if 'climate' in h else h
                x=group['data'][:];y=group['labels_0'][:] if 'labels_0' in group else group['labels'][:]
            assert x.shape==(768,1152,16) and y.shape==(768,1152)
            xs.append(x[::4,::4].transpose(2,0,1).astype(np.float32));ys.append(y[::4,::4].astype(np.int64))
            sources.append({'url':base+split+'/'+name,'sha256':digest(file),'native_shape':list(x.shape)})
            print('CAM5_NATIVE',split,name,flush=True)
        fields[split]=np.stack(xs);labels[split]=np.stack(ys)
    np.save(p/'train_fields.npy',fields['train']);np.save(p/'train_labels.npy',labels['train']);np.save(p/'validation_fields.npy',fields['validation'])
    o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);np.save(o/'validation_labels.npy',labels['validation'])
    manifest(tid,{'source':base,'source_files':sources,'stride':4,'classes':{'0':'background','1':'tropical_cyclone','2':'atmospheric_river'},'deviations':['6train/2officialvalidation CAM5 AllHist fields, native full-domain stride4; small3levelUNet instead ofDeepLabV3+fullscale; noformalquality']})
    freeze(tid,'训练真实气象场的极端天气分割器','''input真实CAM5 All-Hist原生train6/validation2文件的全域stride4，fields形状(N,16,192,288)，train_labels(N,192,288)，0背景/1热带气旋/2大气河流，validation无label。训练CUDA三层U-Net或等价多尺度encoder-decoder，16输入3输出、skip connections，用train字段各通道mean/std归一化，交叉熵，至少5更新并覆盖全部6字段。入口 python solution/main.py train --input input --output output；保存checkpoint.pt含模型/optimizer/RNG/step/归一化，predictions.npy(2,192,288)0..2整数、probabilities.npy(2,3,192,288)、run.json；predict --checkpoint PATH --input NPY --output DIR支持新气象场。独立检查真实labels参与loss、CUDAforward/backward、更新和reload，隐藏IoU另报，不以全部预测背景当正式通过。''')

if __name__=='__main__':
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(f):f.__name__ for f in [cosmos,cam]}
        for future in concurrent.futures.as_completed(futures):
            try:future.result();print('HPC_READY',futures[future],flush=True)
            except Exception as e:print('HPC_FAILED',futures[future],repr(e),flush=True)
