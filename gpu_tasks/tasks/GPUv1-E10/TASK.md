# GPUv1-E10：训练缺失论文引用推荐模型

对真实 Cora 图训练 CUDA GraphSAGE 或 GCN 及链接评分器。input/features.npy 为真实词特征，edges.npy 只提供训练引用边，query_pairs.npy 是混排的隐藏正负候选边（真实 holdout 引用与采样不存在的边），不能把 query_pairs 当成训练图。训练负例从训练图非边采样；至少 5 次优化器更新，固定 seed，GPU 图聚合、反向传播与评分真实执行。
入口 python solution/main.py train --input input --output output；保存 checkpoint.pt（权重、配置、optimizer、step）、query_scores.npy（候选顺序概率）、run.json，支持 python solution/main.py predict --checkpoint output/checkpoint.pt --input input --output output/reloaded.npy。独立验收 hidden AUC >= 0.60、输入全覆盖、概率有限、标准模型重载后结果 <= 1e-5、参数真实更新。不能用候选边训练、直接回传图内边指示或随机分数。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
