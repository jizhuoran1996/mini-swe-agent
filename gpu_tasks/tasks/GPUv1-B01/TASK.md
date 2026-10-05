# GPUv1-B01：适配可重载的图像分类模型

用官方TorchVision ResNet50(/models/torchvision/resnet50.json的预训练权重)微调真实CIFAR10 1000train图/100test图，输入uint8 NHWC32×32×3。resize224，ImageNet mean/std，fc改10类，CUDA交叉熵，全部train图至少一次更新，可以冻结backbone只训练新head以控制debug预算。入口 python solution/main.py train --input input --output output；输出checkpoint.pt含完整参数/optimizer/step/RNG、validation_predictions.npy(100,10)softmax、run.json；predict --checkpoint PATH --input NPY --output NPY新图预测。独立检查真实训练、完整coverage、CUDAforward/backward、head更新与reload；隐藏accuracy独立报告，不能声称ImageNet训练完成。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
