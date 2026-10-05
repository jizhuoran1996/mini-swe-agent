import json
import runpy
import subprocess
import sys
from pathlib import Path
import numpy as np
import torch
from sklearn.metrics import accuracy_score,roc_auc_score

tid=sys.argv[1];short=tid.split('-')[1]
out=Path('/artifacts/output');data=Path('input')
Path('evaluation').mkdir(exist_ok=True)
result={'task_id':tid,'passed':False,'reference_large_tested':False}
if short=='E06':
    x=np.load(data/'vectors.npy',mmap_mode='r');c=np.asarray(np.load(out/'centroids.npy'),dtype=np.float64);a=np.load(out/'assignments.npy');counts=np.load(out/'counts.npy')
    assert c.shape==(32,128) and a.shape==(1000000,) and counts.shape==(32,)
    assert np.isfinite(c).all() and ((a>=0)&(a<32)).all()
    observed=np.bincount(a,minlength=32);assert np.array_equal(observed,counts)
    mean=np.asarray(x,dtype=np.float64).mean(0)
    sse=0.;baseline=0.;sums=np.zeros((32,128));mismatch=0
    for lo in range(0,len(x),16384):
        batch=np.asarray(x[lo:lo+16384],dtype=np.float64)
        d=np.square(batch).sum(1)[:,None]+np.square(c).sum(1)[None,:]-2*batch@c.T
        selected=d[np.arange(len(batch)),a[lo:lo+len(batch)]]
        assert np.all(selected<=d.min(1)+.05+1e-5*np.maximum(d.min(1),1))
        mismatch+=int((a[lo:lo+len(batch)]!=np.argmin(d,axis=1)).sum())
        sse+=float(selected.sum());baseline+=float(np.square(batch-mean).sum())
        np.add.at(sums,a[lo:lo+len(batch)],batch)
    active=observed>0
    center_error=float(np.linalg.norm(c[active]-sums[active]/observed[active,None])/max(np.linalg.norm(c[active]),1))
    assert center_error<=.02,center_error
    assert sse<=.95*baseline,sse/baseline
    np.save('new_vectors.npy',np.asarray(x[[37,2718,900013]]))
    proc=subprocess.run(['python','/artifacts/solution/main.py','assign','--centroids',str(out/'centroids.npy'),'--vectors','new_vectors.npy','--output','evaluation/new_assignments.npy'],capture_output=True,text=True,timeout=60)
    assert proc.returncode==0,proc.stdout+proc.stderr
    new=np.load('evaluation/new_assignments.npy');expected=np.square(np.load('new_vectors.npy')[:,None,:]-c[None,:,:]).sum(2).argmin(1)
    assert np.array_equal(new,expected)
    result.update(rows=len(x),sse=sse,single_center_sse=baseline,sse_ratio=sse/baseline,centroid_mean_relative_error=center_error,near_tie_assignment_rows=mismatch)
    command=['fit','--input','input','--output','evaluation/profile_output']
elif short=='E07':
    e=np.load(data/'edges.npy');n=len(np.load(data/'node_ids.npy'));p=np.load(out/'ranks.npy')
    assert p.shape==(n,) and np.isfinite(p).all() and (p>=0).all() and abs(p.sum()-1)<1e-6
    degree=np.bincount(e[:,0],minlength=n);live=degree>0
    def advance(r):
        return .85*np.bincount(e[:,1],weights=r[e[:,0]]/degree[e[:,0]],minlength=n)+(.15+.85*r[~live].sum())/n
    residual=float(np.abs(p-advance(p)).sum());assert residual<2e-6,residual
    reference=np.ones(n)/n
    for i in range(1000):
        updated=advance(reference)
        if np.abs(updated-reference).sum()<1e-10:reference=updated;break
        reference=updated
    error=float(np.abs(p-reference).sum());assert error<1e-5,error
    proc=subprocess.run(['python','/artifacts/solution/main.py','rank','--input','input','--output','evaluation/resumed','--resume',str(out/'state.npz')],capture_output=True,text=True,timeout=120)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert np.abs(np.load('evaluation/resumed/ranks.npy')-reference).sum()<1e-5
    result.update(nodes=n,edges=len(e),fixed_point_l1=residual,independent_pagerank_l1=error)
    command=['rank','--input','input','--output','evaluation/profile_output']
elif short=='E08':
    e=np.load(data/'edges.npy');n=len(np.load(data/'node_ids.npy'));c=np.load(out/'communities.npy')
    assert c.shape==(n,) and np.issubdtype(c.dtype,np.integer)
    names,inverse=np.unique(c,return_inverse=True);assert len(names)>=2
    degree=np.bincount(e.reshape(-1),minlength=n)
    internal=(c[e[:,0]]==c[e[:,1]])
    mass=np.bincount(inverse,weights=degree,minlength=len(names))
    modularity=float(internal.sum()/len(e)-np.square(mass/(2*len(e))).sum());assert modularity>=.25,modularity
    exported=np.load(out/'cross_edges.npy');expected=e[~internal]
    assert exported.shape==expected.shape
    def edge_ids(edges):return np.sort(np.minimum(edges[:,0],edges[:,1])*n+np.maximum(edges[:,0],edges[:,1]))
    assert np.array_equal(edge_ids(exported),edge_ids(expected))
    proc=subprocess.run(['python','/artifacts/solution/main.py','report','--input','input','--communities',str(out/'communities.npy'),'--output','evaluation/reloaded_report'],capture_output=True,text=True,timeout=60)
    assert proc.returncode==0,proc.stdout+proc.stderr
    result.update(nodes=n,edges=len(e),communities=len(names),modularity=modularity,cross_edges=len(exported))
    command=['cluster','--input','input','--output','evaluation/profile_output']
else:
    name='test_predictions.npy' if short=='E09' else 'query_scores.npy'
    p=np.load(out/name);y=np.load('validation_labels.npy')
    assert np.isfinite(p).all()
    if short=='E09':
        assert p.shape==(len(y),7) and np.allclose(p.sum(1),1,atol=1e-5) and (p>=0).all()
        score=float(accuracy_score(y,p.argmax(1)));assert score>=.4,score
        result['accuracy']=score
    else:
        assert p.shape==y.shape and ((p>=0)&(p<=1)).all()
        score=float(roc_auc_score(y,p));assert score>=.6,score
        result['auc']=score
    proc=subprocess.run(['python','/artifacts/solution/main.py','predict','--checkpoint',str(out/'checkpoint.pt'),'--input','input','--output','evaluation/reloaded.npy'],capture_output=True,text=True,timeout=60)
    assert proc.returncode==0,proc.stdout+proc.stderr
    q=np.load('evaluation/reloaded.npy');assert np.allclose(p,q,atol=1e-5,rtol=1e-5)
    result.update(queries=len(y),reload_max_error=float(np.abs(p-q).max()))
    command=['train','--input','input','--output','evaluation/profile_output']

sys.path.insert(0,'/artifacts/solution')
sys.argv=['/artifacts/solution/main.py']+command
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as profile:
    try:runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
    except SystemExit as e:assert e.code in (0,None)
    torch.cuda.synchronize()
events=[e.name for e in profile.events() if e.device_type==torch.autograd.DeviceType.CUDA]
assert len(events)>=10,events
compute=[n for n in events if not n.lower().startswith(('memcpy','memset'))]
assert len(compute)>=10,events
result.update(passed=True,cuda_kernel_events=len(events),cuda_kernel_names=[n[:250] for n in sorted(set(compute))[:12]])
Path('evaluation/results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='cuda_kernel_names'}))
