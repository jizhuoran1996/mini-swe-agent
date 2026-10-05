"""Prepare genuine bounded source subsets; labels for validation stay outside agents."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import time

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent


def sha(path):
    h = hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(8<<20),b""):
            h.update(b)
    return h.hexdigest()


def higgs():
    task = ROOT / "tasks/GPUv1-E03"
    inputs = task / "input"
    oracle = task / "oracle"
    inputs.mkdir(exist_ok=True)
    oracle.mkdir(exist_ok=True)
    if (oracle/"asset_lock.json").exists():
        print("HIGGS assets already prepared",flush=True)
        return
    url = "https://archive.ics.uci.edu/ml/machine-learning-databases/00280/HIGGS.csv.gz"
    start=time.time()
    count=110000
    data=np.empty((count,29),dtype=np.float32)
    with requests.get(url,stream=True,timeout=(15,60)) as r:
        r.raise_for_status()
        headers={k:r.headers.get(k) for k in ("ETag","Last-Modified","Content-Length")}
        with gzip.GzipFile(fileobj=r.raw) as f:
            for i in range(count):
                line=f.readline()
                if not line:raise ValueError("source was truncated")
                row=np.fromstring(line.decode(),sep=",",dtype=np.float32)
                if len(row)!=29:raise ValueError("wrong HIGGS column count")
                data[i]=row
                if i%10000==0:print("HIGGS source rows",i,flush=True)
    assert np.isfinite(data).all() and np.isin(data[:,0],[0,1]).all()
    np.save(inputs/"train_features.npy",data[:100000,1:],allow_pickle=False)
    np.save(inputs/"train_labels.npy",data[:100000,0].astype(np.int32),allow_pickle=False)
    np.save(inputs/"validation_features.npy",data[100000:,1:],allow_pickle=False)
    np.save(oracle/"validation_labels.npy",data[100000:,0].astype(np.int32),allow_pickle=False)
    m={"task_id":"GPUv1-E03","scale":"debug_real_100k_train_10k_validation","source":url,"source_headers":headers,"train_source_rows":[0,100000],"validation_source_rows":[100000,110000],"features":28,"dtype":"float32","validation_labels_exposed":False,"formal_source_split":False,"deviations":["110K-row streaming source subset. Formal uses the complete 11M source and its declared reference split."],"files":{p.name:sha(p) for p in inputs.glob('*.npy')},"elapsed_preparation_seconds":time.time()-start}
    (inputs/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
    (oracle/"asset_lock.json").write_text(json.dumps(m,indent=2)+"\n")
    print(json.dumps(m,indent=2),flush=True)


if __name__=="__main__":
    higgs()
