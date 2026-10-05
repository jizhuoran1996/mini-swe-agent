# GPUv1-B03 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

为 COCO 图像训练可区分同类不同实例的分割模型，交付可重载模型和保留 image/instance 身份的轮廓文件，并为验证图像生成可直接消费的 mask 和对象框。

### 来源和工作范围

Detectron2 configs/COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml; COCO train2017/val2017; ImageNet R50 backbone initialization.

### 交付要求

- 实例分割 checkpoint 与训练状态
- COCO 格式 prediction JSON/RLE
- 独立 infer.py
- 模型/输入哈希及验证报告

### 必须完成的工作

- 按 COCO 实例标注构建训练输入，执行源 3x 训练计划。
- 保存包含 mask head 的最终模型和训练状态。
- 对完整 val2017 执行 GPU 实例分割，导出 COCO RLE mask、框和类别。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

从交付模型生成指定图片的透明对象裁剪和实例面积表，保持实例编号与原预测可追溯。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
