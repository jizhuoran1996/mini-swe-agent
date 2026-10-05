import json,sys,subprocess,runpy,time,urllib.request
from pathlib import Path
import numpy as np
import torch

tid=sys.argv[1];kind=tid.split('-')[1];out=Path('/artifacts/output');Path('evaluation').mkdir(exist_ok=True)
report={'task_id':tid,'passed':False,'reference_large_tested':False}
def execute(command):
    p=subprocess.run(['python','/artifacts/solution/main.py']+command,capture_output=True,text=True,timeout=120);assert p.returncode==0,p.stdout+p.stderr
if kind=='E01':
    source=np.load('input/lineitem.npy');gold=json.loads(Path('references.json').read_text());pred=json.loads((out/'queries.json').read_text())
    names=['sum_qty','sum_base_price','sum_disc_price','sum_charge','avg_qty','avg_price','avg_disc','count']
    groups=pred['Q1']['groups'];assert len(groups)==len(gold['q1'])
    for row,ref in zip(groups,gold['q1']):
        assert [row['returnflag'],row['linestatus']]==ref[:2]
        assert np.allclose([row[k] for k in names],ref[2:],rtol=1e-8,atol=1e-7)
    q6=pred['Q6'];value=q6.get('revenue',q6.get('sum_extendedprice_discount')) if isinstance(q6,dict) else q6;assert np.isclose(value,gold['q6'],rtol=1e-8)
    command=['query','--state',str(out),'--start-date','1993-01-01','--end-date','1996-01-01','--discount-low','.04','--discount-high','.08','--quantity-limit','17','--output','evaluation/new.json'];execute(command)
    lo=(np.datetime64('1993-01-01')-np.datetime64('1970-01-01')).astype(int);hi=(np.datetime64('1996-01-01')-np.datetime64('1970-01-01')).astype(int)
    live=(source[:,4]>=lo)&(source[:,4]<hi)&(source[:,2]>=.04)&(source[:,2]<=.08)&(source[:,0]<17);expected=float((source[live,1]*source[live,2]).sum());new=json.loads(Path('evaluation/new.json').read_text());actual=new.get('revenue',new.get('sum_extendedprice_discount',new.get('Q6',{}).get('sum_extendedprice_discount')));assert np.isclose(actual,expected,rtol=1e-8)
    report.update(rows=len(source),q1_groups=len(groups),q6=value,new_condition_revenue=actual)
elif kind=='E02':
    rows=[json.loads(x) for x in Path('input/train.jsonl').read_text().splitlines()];val=[json.loads(x) for x in Path('input/validation.jsonl').read_text().splitlines()];schema=json.loads(Path('input/schema.json').read_text());dense=schema['dense_columns'];cats=schema['categorical_columns']
    values=np.asarray([[float(r[k]) if r[k] is not None else 0 for k in dense] for r in rows]);mean=values.mean(0);std=values.std(0);std[std==0]=1
    dictionaries=[{v:i+1 for i,v in enumerate(sorted({str(r[k]) for r in rows if r[k] is not None}))} for k in cats]
    def reference(records):
        numeric=np.asarray([[float(r.get(k) or 0) for k in dense] for r in records]);ids=np.asarray([[dictionaries[j].get(str(r.get(k)),0) if r.get(k) is not None else 0 for j,k in enumerate(cats)] for r in records]);return np.concatenate([(numeric-mean)/std,ids],axis=1)
    errors=[]
    for records,file in [(rows,'train_features.npy'),(val,'validation_features.npy')]:
        p=np.load(out/file);ref=reference(records);assert p.shape==ref.shape and np.allclose(p,ref,atol=1e-5,rtol=1e-5);errors.append(float(np.abs(p-ref).max()))
    assert np.array_equal(np.load(out/'train_labels.npy'),np.asarray([r[schema['label_column']] for r in rows]))
    new={k:None for k in dense+cats};new[cats[0]]='__UNSEEN_CATEGORY_FOR_EVALUATION__';Path('new.jsonl').write_text(json.dumps(new)+'\n')
    command=['transform','--preprocessor',str(out/'preprocessor.json'),'--input','new.jsonl','--output','evaluation/new.npy'];execute(command);assert np.allclose(np.load('evaluation/new.npy'),reference([new]),atol=1e-5)
    report.update(train_rows=len(rows),validation_rows=len(val),max_reference_errors=errors,unknown_category_id=0)
    command=['fit','--input','input','--output','evaluation/profile_fitted']
elif kind=='E04':
    import xgboost as xgb
    x=np.load('input/validation_features.npy');p=np.load(out/'validation_predictions.npy');y=np.load('validation_labels.npy');assert p.shape==y.shape and np.isfinite(p).all()
    model=xgb.Booster();model.load_model(out/'model.json');model.set_param({'device':'cuda'});ref=model.inplace_predict(x);assert np.allclose(ref,p,atol=1e-5)
    report.update(validation_rows=len(p),hidden_rmse=float(np.sqrt(np.square(p-y).mean())),train_mean_baseline_rmse=float(np.sqrt(np.square(np.load('input/train_targets.npy').mean()-y).mean())))
    command=['train','--input','input','--output','evaluation/profile_training']
elif kind=='E05':
    base=np.load('input/base.npy',mmap_mode='r');q=np.load('input/queries.npy');p=np.load(out/'indices.npy');dist=np.load(out/'squared_distances.npy');truth=np.load('neighbors.npy')[:,:10]
    assert p.shape==dist.shape==(10000,10) and np.issubdtype(p.dtype,np.integer) and ((p>=0)&(p<len(base))).all() and np.isfinite(dist).all()
    recall=float(np.mean([len(set(a)&set(b))/10 for a,b in zip(p,truth)]));assert recall>=.95,recall
    for lo in range(0,len(q),100):
        exact=np.square(np.asarray(base[p[lo:lo+100]],dtype=np.float64)-q[lo:lo+100,None,:]).sum(2);assert np.allclose(exact,dist[lo:lo+100],atol=.1,rtol=1e-5)
    # Perturbed source queries are absent from both input and delivered answer files.
    new=q[[37,91,2718,9001]].astype(np.float64).copy();new[:,0]+=.173;np.save('new.npy',new.astype(np.float32))
    best_d=np.full((4,10),np.inf);best_i=np.zeros((4,10),dtype=np.int64)
    for lo in range(0,len(base),16384):
        x=np.asarray(base[lo:lo+16384],dtype=np.float64);d=np.square(x).sum(1)[None,:]+np.square(new).sum(1)[:,None]-2*new@x.T
        top=np.argpartition(d,9,axis=1)[:,:10];candidate_d=np.concatenate([best_d,np.take_along_axis(d,top,1)],1);candidate_i=np.concatenate([best_i,top+lo],1);take=np.argsort(candidate_d,axis=1)[:,:10];best_d=np.take_along_axis(candidate_d,take,1);best_i=np.take_along_axis(candidate_i,take,1)
    command=['query','--index',str(out/'index'),'--queries','new.npy','--output','evaluation/new'];execute(command);nd=np.load('evaluation/new/squared_distances.npy');ni=np.load('evaluation/new/indices.npy');assert np.allclose(nd,best_d,atol=.15,rtol=1e-5)
    actual=np.square(np.asarray(base[ni],dtype=np.float64)-new[:,None,:]).sum(2);assert np.allclose(actual,nd,atol=.15,rtol=1e-5)
    log=open('evaluation/service.log','w');proc=subprocess.Popen(['python','/artifacts/solution/main.py','serve','--index',str(out/'index'),'--port','8157'],stdout=log,stderr=log)
    try:
        ready=False
        for _ in range(120):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8157/health',timeout=1) as r:health=json.load(r);ready=True;break
            except Exception:time.sleep(.25)
        assert ready and proc.poll() is None,Path('evaluation/service.log').read_text()[-2000:]
        for round in range(2):
            req=urllib.request.Request('http://127.0.0.1:8157/search',data=json.dumps({'vectors':new.tolist(),'k':10}).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=30) as r:reply=json.load(r)
            assert np.allclose(np.asarray(reply['squared_distances']),best_d,atol=.15,rtol=1e-5)
            if round==0:time.sleep(3)
    finally:proc.terminate();proc.wait(timeout=10);log.close()
    assert proc.returncode==0;report.update(recall_at_10=recall,queries=10000,new_queries=4,idle_service_rounds=2)
elif kind=='F05':
    from openmm import XmlSerializer,unit
    trajectory=np.load(out/'trajectory.npz');report['trajectory_keys']=trajectory.files
    positions=trajectory['positions'];velocities=trajectory['velocities'];times=trajectory['time'];assert positions.shape[1:]==(14923,3) and velocities.shape==positions.shape and np.isfinite(positions).all() and np.isfinite(velocities).all();assert np.isclose(times[-1],.4)
    state=XmlSerializer.deserialize((out/'state.xml').read_text());assert np.allclose(state.getPositions(asNumpy=True).value_in_unit(unit.nanometer),positions[-1],atol=1e-6)
    assert np.allclose(state.getVelocities(asNumpy=True).value_in_unit(unit.nanometer/unit.picosecond),velocities[-1],atol=1e-6)
    assert (out/'checkpoint.chk').stat().st_size>1000
    command=['resume','--checkpoint',str(out/'checkpoint.chk'),'--artifacts',str(out),'--steps','50','--output','evaluation/continued'];execute(command)
    last=XmlSerializer.deserialize(Path('evaluation/continued/state.xml').read_text());assert np.isclose(last.getTime().value_in_unit(unit.picosecond),.5)
    assert not np.allclose(last.getPositions(asNumpy=True).value_in_unit(unit.nanometer),positions[-1]);report.update(atoms=14923,initial_final_time_ps=float(times[-1]),resumed_time_ps=.5)
else:raise ValueError(kind)
sys.path.insert(0,'/artifacts/solution');sys.argv=['/artifacts/solution/main.py']+command
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
    try:runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
    except SystemExit as e:assert e.code in (0,None)
    torch.cuda.synchronize()
events=[e for e in prof.events() if e.device_type==torch.autograd.DeviceType.CUDA];assert len(events)>=10
report.update(passed=True,cuda_kernel_events=len(events));Path('evaluation/results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
