# GPUv1-E09：训练异构论文图主题分类器

使用真实 Cora 论文节点、引用边及单词节点构成异构图。input/features.npy 是论文词特征，paper_word_edges.npy 是 paper/word 关系，edges.npy 是无向引用边，train_ids/train_labels 是唯一提供的标签，test_ids 为独立验收节点。构建一个 CUDA 异构 GNN，必须同时聚合引用关系和 paper-word 关系，不得只做逐行 MLP。训练至少 5 个 optimizer 更新，使用真实特征与训练标签，固定 seed。
入口 python solution/main.py train --input input --output output；输出 checkpoint.pt（参数和配置、optimizer/step/RNG）、test_predictions.npy（test 顺序的 7 类概率）、run.json（loss/step/结构/耗时）。支持 python solution/main.py predict --checkpoint output/checkpoint.pt --input input --output output/reloaded.npy。隐藏标签要求 accuracy >= 0.40；独立重载预测误差 <= 1e-5，输入覆盖、图关系参与计算及 CUDA forward/backward 必須可观察。禁止用 test 标签训练、只生成已有标签或忽略图关系。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
