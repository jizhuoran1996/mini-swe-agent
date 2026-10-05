# GPUv1-B04 · 建立高分辨率城市道路语义分割模型

Build a high-resolution urban-scene segmenter

**组别**：视觉理解、分割与三维感知　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`cityscapes_segformer_urban_map`

**Workflow family**：`semantic_segmentation_training`

## 任务目标

用 Cityscapes fine 标注训练道路场景语义分割器，为完整验证图像生成原始分辨率的像素类别地图，并交付可再次处理新街景的模型及标签转换工具。

## 具体来源工作负载

MMSegmentation segformer_mit-b2_8xb1-160k_cityscapes-1024x1024.py; Cityscapes fine train/val; MiT-B2 initialization.

## 输入与配置

- dataset: Cityscapes；split: fine train and val；assets: leftImg8bit_trainvaltest 与 gtFine_trainvaltest 对应文件
- config: segformer_mit-b2_8xb1-160k_cityscapes-1024x1024.py；initial_weights: MiT-B2 source checkpoint

## 需要完成的工作

- 冻结 train ID/raw ID 映射和 ignored 类规则。
- 按 1024x1024 训练裁剪和源 160k 计划训练 SegFormer。
- 对验证集恢复全图空间布局，导出合法标签 PNG 与每类覆盖面积统计。

## 交付物

- segformer checkpoint 与训练状态
- 每幅 val 图的预测标签 PNG
- 类别映射和批量推理入口
- 验证指标及街景类别面积汇总

## 后续使用与状态

使用同一模型处理指定城市的后续图像清单，并从真实分割图生成可通行区域面积摘要；复用模型，不重训。

## 独立验收

- 检查每个像素输出尺寸、Cityscapes label ID、ignored 类及图像 ID。
- 独立重算混淆矩阵与 mIoU，质量容差以固定参考模型/训练校准。
- 抽样比较全图预测与实际模型输出，面积摘要必须来自 mask。

## 应拒绝的失败方式

- 只保存缩略图而未恢复原图
- 混淆 train IDs 与原始 IDs
- 丢掉困难图像或 ignored 区域规则
- 输出面积表而无逐像素地图

## 规模配方

### Debug：仅调通

- **data**：固定小批真实城市图像
- **schedule**：短训练/推理只调通 label 与 resize

### Reference large：正式生产规模

- **data**：完整 Cityscapes fine train 和完整 val
- **model_config**：MiT-B2，1024x1024 训练裁剪，160000-iteration 源 schedule
- **hardware_target**：T3：8 张 24–48 GiB GPU，或经参考校准的等效 batch 适配；未实测
- **useful_output**：完整高分辨率语义地图及可重载分割器

### 可选扩展：同一任务的变体

- **data**：相同数据和有效训练计划
- **hardware_target**：较少 GPU 的梯度累积属于运行适配；需记录数值差异
- **not_new_task**：True

## GPU工作与预期资源形态

高分辨率稠密特征和梯度提供显存工作集与持续计算，验证阶段产生全图 D2H/磁盘输出。

## 资源标签（待画像验证）

- high_resolution_training
- dense_prediction
- activation_memory
- d2h_maps

## 设备能力

- cuda
- optional_amp
- nccl_for_ddp

## 后端要求

- MMSegmentation/MMCV GPU 构建
- 高分辨率图片与标签
- 正式多 GPU 配置的进程/通信支持

## 回放约束

- 按完成事件等待训练与 GPU 推理；保留模型等待期间的真实训练/worker 状态。
- 固定全图推理方式，不能后端间改变滑窗以静默降低成本。

## Builder需要实现的部分

- 解析父配置并冻结完整 effective config
- 构建 Cityscapes IDs 与全图验证器
- 测量并校准高分辨率正式画像

## 与相关任务的边界

目标是道路、建筑等稠密语义区域，忽略实例身份；区别于 B03 对象实例轮廓。

## 数据血缘

- cityscapes

## 任务范围与条件

- 数据访问需遵守 Cityscapes 条件。
- 160k 源训练是长任务，建议单独归入 long-training 池。

## 来源记录

- [B_SEGFORMER] SegFormer Cityscapes config — [来源](https://github.com/open-mmlab/mmsegmentation/blob/main/configs/segformer/segformer_mit-b2_8xb1-160k_cityscapes-1024x1024.py)；检查位置：MiT-B2 Cityscapes 1024x1024 config and parent reference
- [B_CITYSCAPES] Cityscapes dataset overview — [来源](https://www.cityscapes-dataset.com/dataset-overview/)；检查位置：Dataset overview

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
