"""Independent Python package consumers; only submitted target wheels are installed."""
import json
import hashlib
from pathlib import Path
from grader_inside import ARTIFACTS, WORK, INSTALL, execute

PACKAGES = {
 'F01':'torch','F02':'tensorflow','F03':'jaxlib','F04':'scikit_learn','F05':'numpy',
 'F06':'scipy','F07':'pandas','F08':'xgboost','F10':'onnxruntime',
}
PROGRAMS = {
'F01':r'''
import torch, tempfile
assert torch.version.cuda is None
x=torch.tensor([[1.,2.],[3.,4.]],requires_grad=True)
y=(x*x).sum();y.backward();assert torch.equal(x.grad,2*x.detach())
m=torch.nn.Linear(2,1);opt=torch.optim.SGD(m.parameters(),lr=.01)
a=torch.tensor([[1.,0.],[0.,1.],[1.,1.]]);b=torch.tensor([[1.],[2.],[3.]])
l0=float(((m(a)-b)**2).mean().detach())
for _ in range(80):opt.zero_grad();loss=((m(a)-b)**2).mean();loss.backward();opt.step()
assert float(loss.detach())<l0
p='new-state.pt';torch.save(m.state_dict(),p);n=torch.nn.Linear(2,1);n.load_state_dict(torch.load(p,weights_only=True));assert torch.allclose(n(a),m(a))
''',
'F02':r'''
import tensorflow as tf
x=tf.Variable([1.,2.,3.])
with tf.GradientTape() as tape:y=tf.reduce_sum(x*x)
assert list(tape.gradient(y,x).numpy())==[2.,4.,6.]
@tf.function
def new_graph(a):return tf.linalg.matmul(a,a)
a=tf.constant([[1.,2.],[3.,4.]]);assert (new_graph(a).numpy()==[[7.,10.],[15.,22.]]).all()
class Model(tf.Module):
 @tf.function(input_signature=[tf.TensorSpec([None],tf.float32)])
 def predict(self,a):return a*3+1
m=Model();tf.saved_model.save(m,'new_saved');n=tf.saved_model.load('new_saved');assert list(n.predict(tf.constant([1.,2.])).numpy())==[4.,7.]
''',
'F03':r'''
import jax,jax.numpy as jnp,numpy as np
assert jax.default_backend()=='cpu'
f=jax.jit(lambda x:jnp.pad(x,((1,1),(2,0)),mode='constant',constant_values=7))
x=jnp.arange(6,dtype=jnp.float32).reshape(2,3)
np.testing.assert_array_equal(np.asarray(f(x)),np.pad(np.arange(6).reshape(2,3),((1,1),(2,0)),constant_values=7))
g=jax.grad(lambda a:jnp.sum(a*a))(jnp.array([2.,3.]));np.testing.assert_array_equal(np.asarray(g),[4.,6.])
''',
'F04':r'''
import numpy as np,pickle
from sklearn.neighbors import KDTree,KNeighborsClassifier
from sklearn.linear_model import LinearRegression
x=np.array([[0.,0.],[1.,0.],[0.,2.],[3.,4.]])
d,i=KDTree(x).query([[.9,.1]],k=2);assert i.tolist()==[[1,0]];np.testing.assert_allclose(d[0],[np.sqrt(.02),np.sqrt(.82)])
c=KNeighborsClassifier(n_neighbors=1).fit(x,[0,1,2,3]);assert c.predict([[.9,.1]]).tolist()==[1]
m=LinearRegression().fit([[0.],[1.],[2.],[3.]],[1.,3.,5.,7.]);assert abs(pickle.loads(pickle.dumps(m)).predict([[4.]])[0]-9)<1e-9
''',
'F05':r'''
import numpy as np
A=np.array([[4.,1.],[2.,3.]]);b=np.array([9.,8.]);np.testing.assert_allclose(np.linalg.solve(A,b),[1.9,1.4])
u,s,v=np.linalg.svd(A);np.testing.assert_allclose((u*s)@v,A,rtol=1e-12,atol=1e-12)
a=np.arange(1000,dtype=np.int64).reshape(100,10);np.save('new-array.npy',a);assert np.array_equal(np.load('new-array.npy'),a)
assert np.einsum('ij,jk->ik',A,A).tolist()==[[18.,7.],[14.,11.]]
''',
'F06':r'''
import numpy as np
from scipy import linalg,signal,sparse,integrate
A=np.array([[4.,1.],[2.,3.]]);np.testing.assert_allclose(linalg.solve(A,[9.,8.]),[1.9,1.4])
q,r=linalg.qr(A);np.testing.assert_allclose(q@r,A,atol=1e-12)
np.testing.assert_allclose(signal.convolve([1.,2.,3.],[1.,-1.]),[1.,1.,1.,-3.])
s=sparse.csr_matrix(A);sparse.save_npz('new-sparse.npz',s);assert (sparse.load_npz('new-sparse.npz')!=s).nnz==0
assert abs(integrate.quad(lambda x:x*x,0.,1.)[0]-1/3)<1e-12
''',
'F07':r'''
import pandas as pd,numpy as np
x=pd.DataFrame({'key':['a','b','a','b'],'v':[1,2,3,4]})
assert x.groupby('key').v.sum().to_dict()=={'a':4,'b':6}
y=pd.DataFrame({'key':['a','b'],'n':[10,20]});z=x.merge(y,on='key');assert len(z)==4 and int((z.v*z.n).sum())==160
x.to_csv('new.csv',index=False);pd.testing.assert_frame_equal(pd.read_csv('new.csv'),x)
a=pd.date_range('2024-02-28',periods=3,tz='UTC');assert a[1].day==29 and a[2].month==3
''',
'F08':r'''
import numpy as np,xgboost as xgb
x=np.array([[i,i%3] for i in range(60)],dtype=np.float32);y=(x[:,0]>=30).astype(np.float32)
d=xgb.DMatrix(x,label=y);m=xgb.train({'objective':'binary:logistic','max_depth':2,'eta':.5,'nthread':2,'seed':31},d,12)
p=m.predict(d);assert float(((p>.5)==y).mean())>.95
m.save_model('new-model.json');n=xgb.Booster();n.load_model('new-model.json');np.testing.assert_array_equal(n.predict(d),p)
assert len(n.get_dump())==12
''',
'F10':r'''
import numpy as np,onnx,onnxruntime as ort
from onnx import helper,TensorProto
node=helper.make_node('Add',['x','y'],['z'])
g=helper.make_graph([node],'independent',[helper.make_tensor_value_info('x',TensorProto.FLOAT,[2,2]),helper.make_tensor_value_info('y',TensorProto.FLOAT,[2,2])],[helper.make_tensor_value_info('z',TensorProto.FLOAT,[2,2])])
m=helper.make_model(g,opset_imports=[helper.make_opsetid('',13)]);m.ir_version=10;onnx.checker.check_model(m);onnx.save(m,'new.onnx')
s=ort.InferenceSession('new.onnx',providers=['CPUExecutionProvider']);a=np.arange(4,dtype=np.float32).reshape(2,2);np.testing.assert_array_equal(s.run(None,{'x':a,'y':a+1})[0],2*a+1)
''',
}


def distinct_wheels(paths):
    """Accept duplicate copies only when filenames and complete bytes agree."""
    selected = {}
    for path in sorted(paths):
        digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
        if path.name in selected:
            assert selected[path.name][1] == digest, 'different submitted bytes for wheel '+path.name
        else:
            selected[path.name] = (path, digest)
    return [path for path, _ in selected.values()]


def consume_python(short):
    wheel_files=list(ARTIFACTS.rglob('*.whl'))
    prefixes=(PACKAGES[short]+'-', 'tensorflow_cpu-') if short=='F02' else (PACKAGES[short]+'-',)
    target=distinct_wheels([p for p in wheel_files if p.name.lower().startswith(prefixes)])
    assert len(target)==1, 'exactly one submitted target wheel required: '+str(target)
    venv=WORK/'venv';execute(['/usr/bin/python3','-m','venv',venv])
    python=venv/'bin/python'
    install=[python,'-m','pip','install','--no-index','--find-links','/opt/wheelhouse']
    for parent in sorted({p.parent for p in wheel_files}):install += ['--find-links',parent]
    # JAX requires both its source-built Python package and the source-built native wheel.
    selected=target
    if short=='F03':
        jax=distinct_wheels([p for p in wheel_files if p.name.startswith('jax-')]);assert len(jax)==1;selected += jax
    if short=='F10':
        selected += ['onnx==1.17.0']
    constraints = ['numpy==2.2.6'] if short=='F07' else []
    execute(install+selected+constraints,timeout=300)
    module={'scikit_learn':'sklearn'}.get(PACKAGES[short],PACKAGES[short])
    prelude='import pathlib,importlib\nm=importlib.import_module('+repr(module)+')\np=pathlib.Path(m.__file__).resolve()\nassert '+repr(str(venv))+' in str(p),str(p)\nassert list(p.parent.rglob("*.so")),"compiled native extension missing"\n'
    program=WORK/'new_consumer.py';program.write_text(prelude+PROGRAMS[short]+'\nprint("independent numerical/serialization consumer passed")\n')
    return execute([python,program],timeout=300).stdout.decode()

CONSUMERS={'BUILDv1-'+short:(lambda short=short:consume_python(short)) for short in PACKAGES}
