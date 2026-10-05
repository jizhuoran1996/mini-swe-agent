# GPUv1-E07：计算真实 Twitter 关注图节点优先级

输入是 SNAP Twitter ego-network union 的完整有向关注边，共 81306 个节点、2420766 条边，input/edges.npy 的两列是 source/target 的稠密节点下标，node_ids.npy 保存原始 ID。在 CUDA 上计算 PageRank，alpha=0.85，均匀 teleport，dangling mass 均匀分配；起始向量均匀，迭代至 L1 差 < 1e-7 或最多 1000 次。主迭代的边贡献和归约必须在 GPU 执行。
入口 python solution/main.py rank --input input --output output。交付 ranks.npy 与节点顺序一致、top_nodes.json（前 100 按排名下降、平分用原始 ID 升序）、state.npz（当前 ranks、iteration、alpha、图哈希）、run.json 和完整代码。支持 rank 增加 --resume output/state.npz，对同一图续算。独立 SciPy CPU oracle 检查总和 1、非负、固定点 L1 残差 < 2e-6、排名差 L1 < 1e-5，重载续算不改图或 ID 映射。禁止 CPU PageRank 后只拷贝结果到 GPU。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
