# GPUv1-B03：适配实例分割模型并导出真实对象轮廓

用 TorchVision Mask R-CNN ResNet50-FPN，初始化权重由 /models/torchvision/maskrcnn.json 指定。input/train_annotations.json 是 12 张真实图的原始 COCO instance boxes/polygons，images.json 共 16 张；余下 4 张只有图像，没有标签。用 pycocotools 解码真实 mask，在 CUDA 上至少对全部 12 个训练图各执行一次有效优化器更新；min_size=320/max_size=640，类别使用原始 COCO 91-ID 约定。
入口 python solution/main.py train --input input --output output；python solution/main.py predict --checkpoint output/checkpoint.pt --input input --output output/reloaded。保存 checkpoint.pt（完整标准 TorchVision state_dict、模型配置、optimizer/step/RNG），每幅完整图的预测 boxes/labels/scores/mask RLE 到 instances.json，并输出 contours.json（从预测二值 mask 提取原图坐标外轮廓），run.json。推理 score threshold=0.25、mask threshold=0.5。独立检查权重变化、真实 CUDA mask loss/backward、标准重载一致、mask/box/轮廓一致和覆盖；未训练初始化权重、不使用 segmentation 标注、二维 boxes 冒充 masks 均失败。小样本质量只报告。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
