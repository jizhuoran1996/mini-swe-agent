# GPUv1-E02：交付可复用的推荐特征处理流水线

input/train.jsonl/validation.jsonl是真实Criteo_x1行，字段由schema.json给定。拟合训练集preprocessor：13数值缺失填0并作训练均值/标准差标准化（std为0时1）；26类别每列按string值排序建立ID从1开始，缺失/未知0。数值统计、标准化和最终特征tensor操作必须CUDA，类别字典可CPU构造。入口 python solution/main.py fit --input input --output output；输出preprocessor.json、train_features.npy(1000,39)float32、validation_features.npy(100,39)、train_labels.npy及run.json；transform --preprocessor PATH --input JSONL --output NPY 能处理新数据。独立按明确公式重算全部值、类别映射、未知/null负例、持久化重载、CUDA归约，不得仅复制源文件。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
