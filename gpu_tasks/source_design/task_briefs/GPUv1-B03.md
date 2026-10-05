# GPUv1-B03 · 训练 COCO 实例分割与对象轮廓导出

Train COCO instance segmentation and export object masks

**组别**：视觉理解、分割与三维感知　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`coco2017_mask_rcnn_instance_masks`

**Workflow family**：`instance_segmentation_training`

## 任务目标

为 COCO 图像训练可区分同类不同实例的分割模型，交付可重载模型和保留 image/instance 身份的轮廓文件，并为验证图像生成可直接消费的 mask 和对象框。

## 具体来源工作负载

Detectron2 configs/COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml; COCO train2017/val2017; ImageNet R50 backbone initialization.

## 输入与配置

- dataset: COCO 2017；split: train2017 and val2017；annotations: instances_train2017.json and oracle-only instances_val2017.json
- config: mask_rcnn_R_50_FPN_3x.yaml；initial_weights: ImageNetPretrained/MSRA/R-50.pkl

## 需要完成的工作

- 按 COCO 实例标注构建训练输入，执行源 3x 训练计划。
- 保存包含 mask head 的最终模型和训练状态。
- 对完整 val2017 执行 GPU 实例分割，导出 COCO RLE mask、框和类别。

## 交付物

- 实例分割 checkpoint 与训练状态
- COCO 格式 prediction JSON/RLE
- 独立 infer.py
- 模型/输入哈希及验证报告

## 后续使用与状态

从交付模型生成指定图片的透明对象裁剪和实例面积表，保持实例编号与原预测可追溯。

## 独立验收

- 重新加载 mask head 和 backbone；检查 val 图片全集、实例类别、RLE 可解码性和原图尺寸。
- 从实际预测重算 mask AP 与 box AP，使用参考校准的容差。
- 抽样重推理并验证 RLE、面积和裁剪对应同一实例。

## 应拒绝的失败方式

- 只交付检测框而没有 mask
- 把多个同类物体合成一个语义区域
- 用标注替代预测
- 导出时图像坐标和 RLE 尺寸错配

## 规模配方

### Debug：仅调通

- **data**：冻结的 COCO 训练/验证小子集
- **schedule**：仅 smoke 验证，不视作正式大训练

### Reference large：正式生产规模

- **data**：完整 COCO train2017 和 val2017
- **model_config**：R50-FPN 3x；270000 iterations，源有效 batch 和调度语义
- **hardware_target**：T3：4–8 张 24–48 GiB GPU；数据并行；工程目标未测
- **useful_output**：实例分割模型与完整验证 mask

### 可选扩展：同一任务的变体

- **data**：同一全量 COCO 与训练计划
- **hardware_target**：扩展 worker/GPU 数并保持有效 batch，不新增任务 ID
- **not_new_task**：True

## GPU工作与预期资源形态

多尺度图像、ROI/mask heads、反向传播和 RLE 结果导出覆盖训练计算、主机预处理与可写 checkpoint。

## 资源标签（待画像验证）

- training
- roi_ops
- variable_images
- checkpoint_io
- mask_output

## 设备能力

- cuda
- torchvision_or_detectron_cuda_ops
- optional_nccl

## 后端要求

- Detectron2 及其已构建 CUDA 扩展
- COCO 图片与实例标注
- 分布式运行时的共享内存和通信

## 回放约束

- 所有训练与 mask 推理重新执行。
- 记录混合精度、ROI/NMS 语义与数据增强；mask 指标不按文件字节相等判定。

## Builder需要实现的部分

- 构建锁定的 Detectron2 镜像
- 包装 COCO RLE 验证与真实裁剪交付
- 参考运行校准质量和耗时

## 与相关任务的边界

学习并输出每个对象实例的像素轮廓，而非 B02 的对象框目录或 B04 的每像素语义类。

## 数据血缘

- coco2017

## 任务范围与条件

- 全训练较长；可先以验证导出通路排错，再采集正式训练轨迹。

## 来源记录

- [B_DETECTRON] Detectron2 model zoo — [来源](https://github.com/facebookresearch/detectron2/blob/main/MODEL_ZOO.md)；检查位置：Common Settings for COCO Models; reproduction entry points
- [B_MASKRCNN_CONFIG] COCO instance segmentation config — [来源](https://github.com/facebookresearch/detectron2/blob/main/configs/COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml)；检查位置：Mask R-CNN R50 FPN 3x config

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
