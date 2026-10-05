# GPUv1-F01：从真实宇宙模拟体数据训练可重载参数估计器

input/train_fields.npy为4个真正CosmoFlow TFv2 128×128×128×4 int16粒子数裁块，train_targets.npy为对应4个归一化宇宙参数；validation_fields.npy两个源val裁块无label。CUDA真实3DCNN：先log1p(max(count,0))，各样本除自身均值（零时1），卷积/池化编码3D全部四个redshift通道，回归4参数，MSE，至少5优化器更新且所有train样本覆盖；每参数输出限制[-1,1]或记录未限制。入口 python solution/main.py train --input input --output output；保存checkpoint.pt含模型config/参数/optimizer/step/RNG，validation_predictions.npy(2,4)、run.json；predict --checkpoint PATH --input NPY --output NPY支持新体数据。独立检查source标签绑定、真实CUDA3Dforward/backward、checkpoint变化、重载预测和隐藏MSE报告，不要求4样本收敛到正式MAE阈值。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
