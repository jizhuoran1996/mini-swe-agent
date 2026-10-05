"""Independent acceptance: hidden labels, standard model reload, new process,
and CUDA kernel evidence for the solver's actual training entry point."""
import json
import runpy
import subprocess
import sys
from pathlib import Path
import numpy as np
import torch
import xgboost as xgb
from sklearn.metrics import roc_auc_score

Path('evaluation').mkdir(exist_ok=True)
out=Path('/artifacts/output')
x=np.load('input/validation_features.npy')
y=np.load('validation_labels.npy')
p=np.load(out/'validation_predictions.npy')
assert p.shape==y.shape==(10000,)
assert np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
auc=float(roc_auc_score(y,p));assert auc>=.65,auc
b=xgb.Booster();b.load_model(out/'model.json');b.set_param({'device':'cpu','nthread':4})
reference=b.predict(xgb.DMatrix(x))
assert np.allclose(p,reference,atol=1e-6,rtol=1e-5)
assert b.num_boosted_rounds()>=32
np.save('new_events.npy',np.load('input/train_features.npy',mmap_mode='r')[700:733])
proc=subprocess.run(['python','/artifacts/solution/main.py','predict','--model',str(out/'model.json'),'--features','new_events.npy','--output','evaluation/new_predictions.npy'],capture_output=True,text=True,timeout=60)
assert proc.returncode==0,proc.stdout+proc.stderr
fresh=np.load('evaluation/new_predictions.npy')
assert np.allclose(fresh,b.predict(xgb.DMatrix(np.load('new_events.npy'))),atol=1e-6,rtol=1e-5)

# XGBoost CUDA kernels are observed by CUPTI, not inferred from the device flag.
sys.argv=['/artifacts/solution/main.py','train','--input','input','--output','evaluation/profile_output']
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as profiler:
    try:
        runpy.run_path('/artifacts/solution/main.py',run_name='__main__')
    except SystemExit as exc:
        assert exc.code in (None,0),exc.code
    torch.cuda.synchronize()
events=[e for e in profiler.events() if e.device_type==torch.autograd.DeviceType.CUDA]
names=sorted(set(e.name for e in events))
assert any('hist' in n.lower() or 'xgboost' in n.lower() or 'gradient' in n.lower() for n in names),names
report={'passed':True,'auc':auc,'rows':10000,'trees':b.num_boosted_rounds(),'max_reload_prediction_error':float(np.max(np.abs(p-reference))),'fresh_process_new_events':len(fresh),'cuda_kernel_events':len(events),'cuda_kernel_names':names[:80],'reference_large_tested':False}
Path('evaluation/results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
