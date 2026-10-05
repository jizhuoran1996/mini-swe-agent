# GPUv1-B04：适配可重载的道路场景分割模型

input有24train/8heldout真实Cityscapes图片，512×256，train label是19类trainID/255ignore。CUDA微调 /models/nvidia--segformer-b0-finetuned-cityscapes-1024-1024 的 SegformerForSemanticSegmentation，全部train至少一次更新，交叉熵ignore255；输入AutoImageProcessor但关闭resize，输出logits插值到原图尺寸。入口 python solution/main.py train --input input --output output；保存HF checkpoint、optimizer/step/RNG的training_state.pt、predictions.npy(8,256,512)int32、run.json；predict --checkpoint PATH --input validation.jsonl --output NPY 重载预测。独立检查真实权重改变、coverage、reload、CUDA backward和隐藏mIoU。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
