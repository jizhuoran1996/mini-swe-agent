# GPUv1-A07：交付可重载的点击率预测网络

input/train.jsonl有1000条真实Criteo_x1记录，13数值/26类别，schema.json明确字段；100条validation隐藏label。训练真实CUDA DLRM：数值bottom MLP到8维，每类别独立8维embedding，26embedding+1dense取所有pairwise dot interactions接top MLP输出logit，BCEWithLogitsLoss；每训练行至少一次更新，固定seed，类别字典仅从train构建，未知类别0，保存数值归一化。入口 python solution/main.py train --input input --output output；输出checkpoint.pt含模型/优化器/step/RNG/preprocessor、validation_predictions.npy(100,)概率、run.json。支持 predict --checkpoint PATH --input JSONL --output NPY 新数据。独立检查结构interaction和26表、真实参数改变、inputcoverage、finite BCE、reload与CUDA backward，AUC独立报告不设tiny实例质量门槛。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
