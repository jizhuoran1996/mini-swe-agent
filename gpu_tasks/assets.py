"""Trusted source acquisition with immutable revisions and bounded storage."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import time

import requests

ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'assets'
ASSETS.mkdir(exist_ok=True)


def digest(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for chunk in iter(lambda:f.read(8<<20),b''):h.update(chunk)
    return h.hexdigest()


def fetch(url,target,max_bytes=8*2**30):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():return target
    if shutil.disk_usage(ROOT).free<50*2**30:raise RuntimeError('host disk reserve prevents download')
    part=target.with_suffix(target.suffix+'.part')
    size=0
    try:
        with requests.get(url,stream=True,timeout=(15,60)) as r:
            r.raise_for_status()
            if int(r.headers.get('Content-Length',0))>max_bytes:raise RuntimeError('source file exceeds download budget')
            with part.open('wb') as f:
                for block in r.iter_content(8<<20):
                    size+=len(block)
                    if size>max_bytes:raise RuntimeError('source file exceeds download budget')
                    if shutil.disk_usage(ROOT).free<50*2**30:raise RuntimeError('disk reserve reached')
                    f.write(block)
        part.rename(target)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return target


def model(repo_id):
    api=requests.get('https://huggingface.co/api/models/'+repo_id,timeout=30)
    api.raise_for_status();info=api.json();revision=info['sha']
    out=ASSETS/'models'/repo_id.replace('/','--')
    out.mkdir(parents=True,exist_ok=True)
    selected=[x['rfilename'] for x in info['siblings'] if '/' not in x['rfilename'] and x['rfilename'].endswith(('.json','.safetensors','.model','.spm','.txt'))]
    if not any(x.endswith('.safetensors') for x in selected):
        selected += [x['rfilename'] for x in info['siblings'] if x['rfilename']=='pytorch_model.bin']
    records=[]
    for name in selected:
        p=fetch(f'https://huggingface.co/{repo_id}/resolve/{revision}/{name}',out/name)
        records.append({'name':name,'bytes':p.stat().st_size,'sha256':digest(p)})
    lock={'repo_id':repo_id,'revision':revision,'source':'https://huggingface.co/'+repo_id,'files':records,'trust_remote_code':False}
    (out/'asset_lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    print('MODEL READY',repo_id,revision,sum(x['bytes'] for x in records),flush=True)
    return out


def dataset_rows(dataset,config,split,count):
    rows=[]
    for offset in range(0,count,100):
        last=None
        for attempt in range(3):
            try:
                r=requests.get('https://datasets-server.huggingface.co/rows',params={'dataset':dataset,'config':config,'split':split,'offset':offset,'length':min(100,count-offset)},timeout=(15,90))
                r.raise_for_status();d=r.json()
                if not d.get('rows'):raise ValueError('source has no rows')
                rows.extend(d['rows']);last=None;break
            except Exception as e:
                last=e
        if last:raise last
    return rows


def first_language_assets():
    task=ROOT/'tasks/GPUv1-A01';inputs=task/'input';oracle=task/'oracle'
    inputs.mkdir(exist_ok=True);oracle.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        mf=pool.submit(model,'HuggingFaceTB/SmolLM2-135M-Instruct')
        train=dataset_rows('HuggingFaceH4/ultrachat_200k','default','train_sft',64)
        validation=dataset_rows('HuggingFaceH4/ultrachat_200k','default','test_sft',16)
        model_dir=mf.result()
    for name,rows in [('train.jsonl',train),('validation.jsonl',validation)]:
        (inputs/name).write_text(''.join(json.dumps({'id':x['row'].get('prompt_id',str(x['row_idx'])),'messages':x['row']['messages']},ensure_ascii=False)+'\n' for x in rows))
    manifest={'task_id':'GPUv1-A01','scale':'debug_64_train_16_validation','dataset':'HuggingFaceH4/ultrachat_200k','config':'default','train_split':'train_sft','validation_split':'test_sft','model_repo':'HuggingFaceTB/SmolLM2-135M-Instruct','model_container_path':'/models/'+model_dir.name,'model_revision':json.loads((model_dir/'asset_lock.json').read_text())['revision'],'max_tokens':256,'deviations':['135M SmolLM2 instead of 7B Mistral; this exercises SFT and checkpoint behavior, not formal model quality','64/16 first stable source rows; truncated token budget 256 instead of formal 2048'],'files':{p.name:digest(p) for p in inputs.glob('*.jsonl')}}
    (inputs/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(oracle/'asset_lock.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('A01 INPUT READY',flush=True)


if __name__=='__main__':
    first_language_assets()
