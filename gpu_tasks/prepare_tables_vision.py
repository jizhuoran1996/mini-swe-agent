import gzip,io,json,pickle,tarfile,os
import numpy as np
from assets import ROOT,ASSETS,fetch,digest
from prepare_graphs import manifest
from specify_ready import freeze

def classification():
    tid='GPUv1-B01';p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True)
    url='https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz';archive=fetch(url,ASSETS/'vision/cifar-10-python.tar.gz',max_bytes=180*2**20)
    # Trusted public dataset pickle is parsed only in a resource-limited CPU container.
    from container import Sandbox
    with Sandbox(tid+'-source-extract',inputs=archive.parent,gpu_enabled=False) as sandbox:
        code="""import tarfile,pickle,numpy as np
from pathlib import Path
Path('output').mkdir()
with tarfile.open('input/cifar-10-python.tar.gz') as a:
 for name,prefix,n in [('data_batch_1','train',1000),('test_batch','validation',100)]:
  d=pickle.load(a.extractfile('cifar-10-batches-py/'+name),encoding='bytes')
  np.save('output/'+prefix+'_images.npy',d[b'data'][:n].reshape(n,3,32,32).transpose(0,2,3,1))
  np.save('output/'+prefix+'_labels.npy',np.asarray(d[b'labels'][:n],dtype=np.int64))
"""
        file=ASSETS/'vision/extract_cifar.py';file.write_text(code);sandbox.put(file,'/workspace/extract.py');result=sandbox.exec('python extract.py');assert result['exit_code']==0,result;sandbox.collect(ASSETS/'vision/cifar_debug')
    source=ASSETS/'vision/cifar_debug/output';o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True)
    for name in ['train_images.npy','train_labels.npy','validation_images.npy']:os.link(source/name,p/name) if not (p/name).exists() else None
    os.link(source/'validation_labels.npy',o/'validation_labels.npy') if not (o/'validation_labels.npy').exists() else None
    manifest(tid,{'source':url,'source_sha256':digest(archive),'deviations':['CIFAR10 native1000train/100test instead ofImageNet; real pretrainedR50initialization10classhead; formalqualitynotclaimed']})
    freeze(tid,'适配可重载的图像分类模型','''用官方TorchVision ResNet50(/models/torchvision/resnet50.json的预训练权重)微调真实CIFAR10 1000train图/100test图，输入uint8 NHWC32×32×3。resize224，ImageNet mean/std，fc改10类，CUDA交叉熵，全部train图至少一次更新，可以冻结backbone只训练新head以控制debug预算。入口 python solution/main.py train --input input --output output；输出checkpoint.pt含完整参数/optimizer/step/RNG、validation_predictions.npy(100,10)softmax、run.json；predict --checkpoint PATH --input NPY --output NPY新图预测。独立检查真实训练、完整coverage、CUDAforward/backward、head更新与reload；隐藏accuracy独立报告，不能声称ImageNet训练完成。''')

def taxi():
    import pyarrow.parquet as pq
    tid='GPUv1-E04';p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True)
    url='https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2019-01.parquet';file=fetch(url,ASSETS/'tables/yellow_tripdata_2019-01.parquet',max_bytes=300*2**20)
    cols=['VendorID','tpep_pickup_datetime','passenger_count','trip_distance','RatecodeID','PULocationID','DOLocationID','fare_amount']
    parts=[];count=0
    for batch in pq.ParquetFile(file).iter_batches(batch_size=65536,columns=cols):
        d=batch.to_pydict();features=np.column_stack([d['VendorID'],d['passenger_count'],d['trip_distance'],d['RatecodeID'],d['PULocationID'],d['DOLocationID'],[v.hour for v in d['tpep_pickup_datetime']],[v.weekday() for v in d['tpep_pickup_datetime']]]).astype(np.float32);target=np.asarray(d['fare_amount'],dtype=np.float32)
        ok=np.isfinite(features).all(1)&np.isfinite(target)&(target>0)&(target<200)&(features[:,2]>0)&(features[:,2]<100)
        parts.append((features[ok],target[ok]));count+=int(ok.sum())
        if count>=55000:break
    x=np.concatenate([a for a,b in parts])[:55000];y=np.concatenate([b for a,b in parts])[:55000];assert len(x)==55000
    np.save(p/'train_features.npy',x[:50000]);np.save(p/'train_targets.npy',y[:50000]);np.save(p/'validation_features.npy',x[50000:]);o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);np.save(o/'validation_labels.npy',y[50000:])
    manifest(tid,{'source':url,'source_sha256':digest(file),'features':cols,'deviations':['first55000validnative2019Jantrips; 50K/5Kordereddebugsplit, notfullTLCformaltraining']})
    freeze(tid,'训练可重载的出租车费用估计器','''真实NYCTLC2019Jan原始行经过明确finite/fare(0,200)/distance(0,100)筛选，input train_features(50000,8)/train_targets和validation_features(5000,8)。训练XGBoost3.0.5 device=cuda tree_method=hist回归fare_amount，最多300trees、max_depth<=8、固定seed；禁CPUfallback。入口 python solution/main.py train --input input --output output；保存model.json、validation_predictions.npy(5000,)、run.json（输入绑定/config/同步耗时），predict --model PATH --input NPY --output NPY支持新数据。独立隐藏RMSE与train均值baseline、标准XGBreload预测、真实CUDA boosting kernels，debug质量只报告。''')

def tpch():
    tid='GPUv1-E01';p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True)
    ext=fetch('https://extensions.duckdb.org/v1.5.6/linux_amd64/tpch.duckdb_extension.gz',ASSETS/'tables/tpch.duckdb_extension.gz',max_bytes=32*2**20)
    target=ext.with_suffix('')
    if not target.exists():
        with gzip.open(ext,'rb') as f:target.write_bytes(f.read(64*2**20))
    from container import Sandbox
    with Sandbox(tid+'-dbgen',inputs=target.parent,gpu_enabled=False) as s:
        code="""import duckdb,numpy as np,json
from pathlib import Path
Path('output').mkdir()
c=duckdb.connect();c.execute("LOAD 'input/tpch.duckdb_extension'");c.execute('CALL dbgen(sf=0.1)')
x=c.execute("SELECT l_quantity,l_extendedprice,l_discount,l_tax,date_diff('day',DATE '1970-01-01',l_shipdate),ascii(l_returnflag),ascii(l_linestatus) FROM lineitem").fetchnumpy()
np.save('output/lineitem.npy',np.column_stack(list(x.values())).astype(np.float64))
q1=c.execute("SELECT l_returnflag,l_linestatus,SUM(l_quantity),SUM(l_extendedprice),SUM(l_extendedprice*(1-l_discount)),SUM(l_extendedprice*(1-l_discount)*(1+l_tax)),AVG(l_quantity),AVG(l_extendedprice),AVG(l_discount),COUNT(*) FROM lineitem WHERE l_shipdate<=DATE '1998-09-02' GROUP BY l_returnflag,l_linestatus ORDER BY l_returnflag,l_linestatus").fetchall()
q6=c.execute("SELECT SUM(l_extendedprice*l_discount) FROM lineitem WHERE l_shipdate>=DATE '1994-01-01' AND l_shipdate<DATE '1995-01-01' AND l_discount BETWEEN .05 AND .07 AND l_quantity<24").fetchone()[0]
Path('output/oracle.json').write_text(json.dumps({'q1':q1,'q6':q6},default=float))
"""
        file=ASSETS/'tables/dbgen.py';file.write_text(code);s.put(file,'/workspace/dbgen.py');r=s.exec('python dbgen.py');assert r['exit_code']==0,r;s.collect(ASSETS/'tables/tpch_debug')
    source=ASSETS/'tables/tpch_debug/output';os.link(source/'lineitem.npy',p/'lineitem.npy') if not (p/'lineitem.npy').exists() else None
    o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);(o/'references.json').write_bytes((source/'oracle.json').read_bytes())
    manifest(tid,{'source':'Official DuckDB TPCH dbgen extension','extension_sha256':digest(target),'scale_factor':.1,'deviations':['native officialbenchmarkgeneratorSF0.1; PyTorch CUDA relational aggregations instead ofcuDFRAPIDS; notarbitrarysyntheticarray']})
    freeze(tid,'交付可继续查询的业务分析结果与设备数据集','''input/lineitem.npy为官方TPC-H dbgen SF0.1原生行，float64列[quantity,extendedprice,discount,tax,shipdate_days_since1970,ASCII_returnflag,ASCII_linestatus]。CUDA float64完整查询Q1：shipdate<=1998-09-02，按returnflag/linestatus排序group，输出sum_qty/sum_base_price/sum_disc_price/sum_charge/avg_qty/avg_price/avg_disc/count；Q6: shipdate>=1994-01-01且<1995-01-01、discount在[.05,.07]、quantity<24求sum(extendedprice*discount)。筛选和group归约在CUDA执行。入口 python solution/main.py run --input input --output output；输出queries.json、dataset.npy或等价完整可重载data、state.json、run.json。query --state output --start-date YYYY-MM-DD --end-date YYYY-MM-DD --discount-low F --discount-high F --quantity-limit F --output JSON返回Q6同语义新条件，不能读取原始input或固定常量答案。独立DuckDB/CPU完整重算两个查询及新条件，relative error<=1e-8，实际CUDA归约。''')

if __name__=='__main__':
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(f):f.__name__ for f in [classification,taxi,tpch]}
        for fut in concurrent.futures.as_completed(fs):
            try:fut.result();print('READY',fs[fut],flush=True)
            except Exception as e:print('PREP_FAILURE',fs[fut],repr(e),flush=True)
