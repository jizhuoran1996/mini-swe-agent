# GPUv1-E04：训练可重载的出租车费用估计器

真实NYCTLC2019Jan原始行经过明确finite/fare(0,200)/distance(0,100)筛选，input train_features(50000,8)/train_targets和validation_features(5000,8)。训练XGBoost3.0.5 device=cuda tree_method=hist回归fare_amount，最多300trees、max_depth<=8、固定seed；禁CPUfallback。入口 python solution/main.py train --input input --output output；保存model.json、validation_predictions.npy(5000,)、run.json（输入绑定/config/同步耗时），predict --model PATH --input NPY --output NPY支持新数据。独立隐藏RMSE与train均值baseline、标准XGBreload预测、真实CUDA boosting kernels，debug质量只报告。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
