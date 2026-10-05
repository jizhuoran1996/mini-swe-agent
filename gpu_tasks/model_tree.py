"""Fetch only one precision of genuine public pipeline components."""
import json
from pathlib import Path
import requests
from assets import ASSETS,fetch,digest

def pipeline_model(repo,precision='fp16'):
    response=requests.get('https://huggingface.co/api/models/'+repo,params={'blobs':'true'},timeout=30);response.raise_for_status();info=response.json();rev=info['sha']
    folder=ASSETS/'models'/repo.replace('/','--');folder.mkdir(parents=True,exist_ok=True)
    files={x['rfilename']:x for x in info['siblings']}
    chosen=[name for name in files if name.endswith(('.json','.txt','.model','.spm','.yaml','.jinja')) and not name.startswith(('onnx/','openvino/','flax/'))]
    components={str(Path(name).parent) for name in files if name.endswith(('.safetensors','.bin','.ckpt')) and not name.startswith(('onnx/','openvino/','flax/'))}
    for parent in sorted(components):
        if parent=='.' and 'model_index.json' in files:
            continue  # Diffusers loads component subfolders, not redundant root checkpoints.
        options=[name for name in files if str(Path(name).parent)==parent and name.endswith(('.safetensors','.bin','.ckpt'))]
        variants=[n for n in options if '.'+precision+'.' in n and n.endswith('.safetensors')]
        native=[n for n in options if n.endswith('.safetensors') and not any(v in n for v in ['.fp16.','.bf16.','.non_ema.'])]
        selected=variants or native or [n for n in options if n.endswith(('.bin','.ckpt')) and not n.startswith(('training','optimizer'))]
        chosen.extend(selected)
    total=sum(files[n].get('size',0) for n in chosen)
    if total>24*2**30:raise ValueError('single pipeline exceeds frozen source acquisition budget')
    records=[]
    for name in sorted(set(chosen)):
        if '..' in Path(name).parts:raise ValueError('unsafe upstream path')
        p=fetch(f'https://huggingface.co/{repo}/resolve/{rev}/{name}',folder/name,max_bytes=12*2**30)
        records.append({'name':name,'sha256':digest(p),'bytes':p.stat().st_size})
    lock={'repo_id':repo,'revision':rev,'precision_selection':precision,'files':records,'source':'https://huggingface.co/'+repo,'trust_remote_code':False}
    aliases=[]
    for record in records:
        path=Path(record['name'])
        if '.fp16.' in path.name:
            alias=path.with_name(path.name.replace('.fp16.','.'))
            if not (folder/alias).exists():(folder/alias).symlink_to(path.name)
            aliases.append({'name':str(alias),'target':str(path),'sha256':record['sha256'],'reason':'Canonical loader name for the same pinned fp16 weight bytes; no extra model or copied weight.'})
    lock['aliases']=aliases
    (folder/'asset_lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    print('PIPELINE_READY',repo,sum(x['bytes'] for x in records),flush=True)
    return folder

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('repos',nargs='+');a=p.parse_args()
    for repo in a.repos:
        try:pipeline_model(repo)
        except Exception as e:print('PIPELINE_FETCH_FAILED',repo,type(e).__name__,str(e)[:300],flush=True)
