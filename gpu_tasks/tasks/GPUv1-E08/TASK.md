# GPUv1-E08：建立真实社交图社区与跨社区连接目录

输入是 SNAP Facebook ego-network union 的完整无向简单图，共 4039 节点、88234 条边。input/edges.npy 每条无向边只给一次，node_ids.npy 是原始节点 ID。构造无向邻接，在 GPU 上用 label propagation、Louvain 局部移动或 spectral 方法检测社区；主要图计算必须真实 CUDA 执行。选择能形成有意义社区的算法和固定 seed，不要求与任何唯一 partition 完全相同。
入口 python solution/main.py cluster --input input --output output；交付 communities.npy (4039,) 整型社区 ID、community_summary.json（社区节点数、内部边数）、cross_edges.npy（跨社区的原始稠密下标边，每条源边一次）、state.npz、run.json。支持 python solution/main.py report --input input --communities output/communities.npy --output output/reloaded_report，在新进程中只用保存分区重算目录。独立检查全覆盖、不少于 2 个非空社区、标准无向 modularity >= 0.25、统计与跨社区边完全正确。人工全单节点、全单社区、任意哈希分区不通过。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
