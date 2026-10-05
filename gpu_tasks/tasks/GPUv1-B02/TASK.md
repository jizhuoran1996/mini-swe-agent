# GPUv1-B02：建立可重载查询的真实目标框目录

用 /models/torchvision/retinanet.json 指定的官方 TorchVision RetinaNet ResNet50-FPN 权重在 CUDA 上检测 input/images.json 清单的 16 张完整 COCO 图像。min_size=320、max_size=640、score threshold=0.25，保留 COCO category ID，不重新训练。入口 python solution/main.py detect --input input --output output；输出 detections.json（每图 image_id/file_name/original_size 和全部 boxes/labels/scores；即使无检测也有记录）、catalog.json（类别映射、图像到结果索引、模型/参数绑定）、run.json。另实现 python solution/main.py query --catalog output/catalog.json --image-id ID，标准输出该图检测 JSON，不依赖原始图像。独立用冻结模型重算 boxes/labels/scores 与排序，检查原图坐标、所有图覆盖、score threshold、跨进程目录查询与 CUDA forward。真实 COCO mAP 单独报告；debug 不等于 OpenImages 全量通过。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
