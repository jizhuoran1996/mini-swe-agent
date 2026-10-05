# GPUv1-F02：训练真实气象场的极端天气分割器

input真实CAM5 All-Hist原生train6/validation2文件的全域stride4，fields形状(N,16,192,288)，train_labels(N,192,288)，0背景/1热带气旋/2大气河流，validation无label。训练CUDA三层U-Net或等价多尺度encoder-decoder，16输入3输出、skip connections，用train字段各通道mean/std归一化，交叉熵，至少5更新并覆盖全部6字段。入口 python solution/main.py train --input input --output output；保存checkpoint.pt含模型/optimizer/RNG/step/归一化，predictions.npy(2,192,288)0..2整数、probabilities.npy(2,3,192,288)、run.json；predict --checkpoint PATH --input NPY --output DIR支持新气象场。独立检查真实labels参与loss、CUDAforward/backward、更新和reload，隐藏IoU另报，不以全部预测背景当正式通过。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
