"""Freeze genuine public graph/vector debug inputs; no generated stand-ins."""
import gzip
import json
import os
from pathlib import Path
import tarfile
import numpy as np
from assets import ROOT,ASSETS,fetch,digest
from specify_ready import freeze

def manifest(tid,metadata):
    task=ROOT/'tasks'/tid
    metadata.update(task_id=tid,scale='debug_only',formal_large_tested=False)
    metadata['files']={p.name:digest(p) for p in (task/'input').iterdir() if p.is_file() and p.name!='manifest.json'}
    (task/'input/manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (task/'oracle').mkdir(exist_ok=True)
    (task/'oracle/asset_lock.json').write_text(json.dumps(metadata,indent=2)+'\n')

def vectors():
    task=ROOT/'tasks/GPUv1-E06';(task/'input').mkdir(exist_ok=True)
    source=ROOT.parent/'pilot_gpu/agent/input/base.npy'
    target=task/'input/vectors.npy'
    if not target.exists():os.link(source,target)
    manifest('GPUv1-E06',{'source':'https://ann-benchmarks.com/sift-128-euclidean.hdf5','shape':[1000000,128],'dataset':'native SIFT1M','deviations':['SIFT1M 128-D rather than DEEP1B 96-D/100M reference; preserves genuine GPU clustering, assignment and continuation']})
    freeze('GPUv1-E06','为真实百万向量生成可复用内容分区','''input/vectors.npy 为 SIFT1M 的 1000000 个真实 128 维 float32 描述子。用 CUDA 上的 K-means（K=32，固定 seed，至少一次 Lloyd 更新，最多 20 次，收敛可提前停）对所有向量聚类，批量距离和分配、质心求和必须真实在 GPU 上执行。不要做全量 N×N 距离。输出 output/centroids.npy (32,128)、assignments.npy (1000000,) int32/int64、counts.npy (32,)、run.json（每轮 SSE、seed、同步计时、覆盖数和配置）。空簇需明确处理。
入口：python solution/main.py fit --input input --output output。另支持 python solution/main.py assign --centroids output/centroids.npy --vectors input/vectors.npy --output output/reassigned.npy，不重新训练。最终分配必须针对最终质心。独立验收检查全覆盖、最近质心分配、计数与 SSE 重算、质心是最终簇的均值（或残差相对基线 ≤ 0.02，允许提前停止后的最后一轮偏差）、SSE 比一个总均值质心下降至少 5%，新进程新向量可分配；检查 CUDA 距离与归约内核。不得只聚类前缀后随机分配其余向量。''')

def graph(tid,url,directed):
    p=fetch(url,ASSETS/'graphs'/url.rsplit('/',1)[-1],max_bytes=64*2**20)
    with gzip.open(p,'rt') as f:
        edges=np.array([tuple(map(int,line.split())) for line in f if not line.startswith('#') and line.strip()],dtype=np.int64)
    ids=np.unique(edges)
    mapped=np.searchsorted(ids,edges)
    task=ROOT/'tasks'/tid;(task/'input').mkdir(exist_ok=True)
    np.save(task/'input/edges.npy',mapped)
    np.save(task/'input/node_ids.npy',ids)
    manifest(tid,{'source':url,'source_sha256':digest(p),'nodes':len(ids),'edges':len(edges),'directed':directed,'deviations':['Native public SNAP ego graph union replaces inaccessible/unbounded formal Twitter2010/Friendster graph; no duplicated rows or fabricated graph']})
    return len(ids),len(edges)

def graphs():
    n,e=graph('GPUv1-E07','https://snap.stanford.edu/data/twitter_combined.txt.gz',True)
    freeze('GPUv1-E07','计算真实 Twitter 关注图节点优先级',f'''输入是 SNAP Twitter ego-network union 的完整有向关注边，共 {n} 个节点、{e} 条边，input/edges.npy 的两列是 source/target 的稠密节点下标，node_ids.npy 保存原始 ID。在 CUDA 上计算 PageRank，alpha=0.85，均匀 teleport，dangling mass 均匀分配；起始向量均匀，迭代至 L1 差 < 1e-7 或最多 1000 次。主迭代的边贡献和归约必须在 GPU 执行。
入口 python solution/main.py rank --input input --output output。交付 ranks.npy 与节点顺序一致、top_nodes.json（前 100 按排名下降、平分用原始 ID 升序）、state.npz（当前 ranks、iteration、alpha、图哈希）、run.json 和完整代码。支持 rank 增加 --resume output/state.npz，对同一图续算。独立 SciPy CPU oracle 检查总和 1、非负、固定点 L1 残差 < 2e-6、排名差 L1 < 1e-5，重载续算不改图或 ID 映射。禁止 CPU PageRank 后只拷贝结果到 GPU。''')
    n,e=graph('GPUv1-E08','https://snap.stanford.edu/data/facebook_combined.txt.gz',False)
    freeze('GPUv1-E08','建立真实社交图社区与跨社区连接目录',f'''输入是 SNAP Facebook ego-network union 的完整无向简单图，共 {n} 节点、{e} 条边。input/edges.npy 每条无向边只给一次，node_ids.npy 是原始节点 ID。构造无向邻接，在 GPU 上用 label propagation、Louvain 局部移动或 spectral 方法检测社区；主要图计算必须真实 CUDA 执行。选择能形成有意义社区的算法和固定 seed，不要求与任何唯一 partition 完全相同。
入口 python solution/main.py cluster --input input --output output；交付 communities.npy ({n},) 整型社区 ID、community_summary.json（社区节点数、内部边数）、cross_edges.npy（跨社区的原始稠密下标边，每条源边一次）、state.npz、run.json。支持 python solution/main.py report --input input --communities output/communities.npy --output output/reloaded_report，在新进程中只用保存分区重算目录。独立检查全覆盖、不少于 2 个非空社区、标准无向 modularity >= 0.25、统计与跨社区边完全正确。人工全单节点、全单社区、任意哈希分区不通过。''')

def cora():
    url='https://linqs-data.soe.ucsc.edu/public/lbc/cora.tgz'
    p=fetch(url,ASSETS/'graphs/cora.tgz',max_bytes=8*2**20)
    with tarfile.open(p) as archive:
        rows=[line.split() for line in archive.extractfile('cora/cora.content').read().decode().splitlines()]
        cites=[line.split() for line in archive.extractfile('cora/cora.cites').read().decode().splitlines()]
    ids=np.array([int(r[0]) for r in rows]);mapping={int(v):i for i,v in enumerate(ids)}
    features=np.array([r[1:-1] for r in rows],dtype=np.float32)
    labels_text=sorted(set(r[-1] for r in rows));labels=np.array([labels_text.index(r[-1]) for r in rows],dtype=np.int64)
    edges=np.array(sorted(set((min(mapping[int(a)],mapping[int(b)]),max(mapping[int(a)],mapping[int(b)])) for a,b in cites if a!=b)),dtype=np.int64)
    rng=np.random.default_rng(2026)
    permutation=rng.permutation(len(ids));train=permutation[:1624];test=permutation[2166:]
    for tid in ['GPUv1-E09','GPUv1-E10']:
        task=ROOT/'tasks'/tid;(task/'input').mkdir(exist_ok=True);(task/'oracle').mkdir(exist_ok=True)
        np.save(task/'input/features.npy',features);np.save(task/'input/node_ids.npy',ids)
    t=ROOT/'tasks/GPUv1-E09'
    np.save(t/'input/edges.npy',edges);np.save(t/'input/train_ids.npy',train);np.save(t/'input/train_labels.npy',labels[train]);np.save(t/'input/test_ids.npy',test);np.save(t/'oracle/validation_labels.npy',labels[test])
    paper_word=np.column_stack(np.nonzero(features)).astype(np.int64);np.save(t/'input/paper_word_edges.npy',paper_word)
    manifest('GPUv1-E09',{'source':url,'source_sha256':digest(p),'dataset':'Cora paper/word heterogeneous graph derived from original binary word features','node_classes':labels_text,'seed':2026,'deviations':['Cora paper-word graph rather than IGBH; word nodes are actual source feature incidences, not invented records']})
    freeze('GPUv1-E09','训练异构论文图主题分类器','''使用真实 Cora 论文节点、引用边及单词节点构成异构图。input/features.npy 是论文词特征，paper_word_edges.npy 是 paper/word 关系，edges.npy 是无向引用边，train_ids/train_labels 是唯一提供的标签，test_ids 为独立验收节点。构建一个 CUDA 异构 GNN，必须同时聚合引用关系和 paper-word 关系，不得只做逐行 MLP。训练至少 5 个 optimizer 更新，使用真实特征与训练标签，固定 seed。
入口 python solution/main.py train --input input --output output；输出 checkpoint.pt（参数和配置、optimizer/step/RNG）、test_predictions.npy（test 顺序的 7 类概率）、run.json（loss/step/结构/耗时）。支持 python solution/main.py predict --checkpoint output/checkpoint.pt --input input --output output/reloaded.npy。隐藏标签要求 accuracy >= 0.40；独立重载预测误差 <= 1e-5，输入覆盖、图关系参与计算及 CUDA forward/backward 必須可观察。禁止用 test 标签训练、只生成已有标签或忽略图关系。''')
    perm=rng.permutation(len(edges));positive=edges[perm[:len(edges)//5]];train_edges=edges[perm[len(edges)//5:]]
    known=set(map(tuple,edges.tolist()));negative=[]
    while len(negative)<len(positive):
        a,b=sorted(rng.integers(0,len(ids),size=2).tolist())
        if a!=b and (a,b) not in known and (a,b) not in negative:negative.append((a,b))
    pairs=np.concatenate([positive,np.array(negative)]);y=np.concatenate([np.ones(len(positive)),np.zeros(len(negative))]);q=rng.permutation(len(pairs))
    t=ROOT/'tasks/GPUv1-E10';np.save(t/'input/edges.npy',train_edges);np.save(t/'input/query_pairs.npy',pairs[q]);np.save(t/'oracle/validation_labels.npy',y[q])
    manifest('GPUv1-E10',{'source':url,'source_sha256':digest(p),'dataset':'Cora held-out real citation edges plus benchmark-sampled genuine nonedges','edge_train_rows':len(train_edges),'query_rows':len(pairs),'seed':2026,'deviations':['Cora instead of full ogbl-citation2; edge holdout frozen, original citations are withheld from training graph']})
    freeze('GPUv1-E10','训练缺失论文引用推荐模型','''对真实 Cora 图训练 CUDA GraphSAGE 或 GCN 及链接评分器。input/features.npy 为真实词特征，edges.npy 只提供训练引用边，query_pairs.npy 是混排的隐藏正负候选边（真实 holdout 引用与采样不存在的边），不能把 query_pairs 当成训练图。训练负例从训练图非边采样；至少 5 次优化器更新，固定 seed，GPU 图聚合、反向传播与评分真实执行。
入口 python solution/main.py train --input input --output output；保存 checkpoint.pt（权重、配置、optimizer、step）、query_scores.npy（候选顺序概率）、run.json，支持 python solution/main.py predict --checkpoint output/checkpoint.pt --input input --output output/reloaded.npy。独立验收 hidden AUC >= 0.60、输入全覆盖、概率有限、标准模型重载后结果 <= 1e-5、参数真实更新。不能用候选边训练、直接回传图内边指示或随机分数。''')

if __name__=='__main__':
    vectors();graphs();cora()
    print('E06-E10 genuine inputs and debug specs frozen',flush=True)
