# GPUv1-B01 · 训练并交付 ImageNet 图像分类模型

Train and deliver an ImageNet image classifier

**组别**：视觉理解、分割与三维感知　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`imagenet1k_resnet50_classifier`

**Workflow family**：`image_classification_training`

## 任务目标

为完整 ImageNet-1K 图像库训练 ResNet-50 分类器，交付能独立重载的模型、标签映射和批量分类入口，并在未参与训练的验证集上生成逐图预测及分类质量报告。

## 具体来源工作负载

TorchVision references/classification/train.py; ResNet-50; ILSVRC2012/ImageNet-1K train and validation splits; reference 90-epoch recipe.

## 输入与配置

- dataset: ILSVRC2012 / ImageNet-1K；split: official train and validation；binding: 获取授权后的原始图片与 devkit，冻结 synset 映射和文件清单
- model: torchvision resnet50；initialization: reference recipe random initialization
- config: references/classification/train.py ResNet defaults；schedule: 90 epochs; batch/learning-rate mapping recorded

## 需要完成的工作

- 检查 train/val 清单与类别目录映射，按上游预处理训练真实图像。
- 执行完整声明训练计划，保存权重、优化器、学习率和数据游标状态。
- 独立重载 checkpoint，对完整验证集推理并交付逐图分类记录。

## 交付物

- model.pth 与完整训练状态
- class_index.json
- predict.py 与锁定配置
- validation_predictions.parquet、重算指标和数据清单

## 后续使用与状态

用交付的模型处理一份预先冻结、来自验证集的复核清单，生成指定类别的错误案例清单；复用模型文件与标签映射，不重新训练。

## 独立验收

- 重新加载模型和配置，核对 1000 类输出与 synset 映射，验证所有 val 图片恰好一条预测。
- 从实际预测重算 top-1/top-5；质量容差由固定参考训练校准并冻结。
- 核对有效训练样本量、状态更新与最终 checkpoint；验证器只做抽样重推理，不代跑完整训练。

## 应拒绝的失败方式

- 提交初始随机模型或伪造训练日志
- 用验证标签直接生成预测
- 跳过某些类别或重复图片补齐数量

## 规模配方

### Debug：仅调通

- **data**：每类固定少量真实训练图和对应验证样本
- **schedule**：短训练仅检查数据、checkpoint 与 oracle；不进入正式资源画像

### Reference large：正式生产规模

- **data**：完整 ImageNet-1K train；完整 validation
- **model_config**：ResNet-50，90-epoch 源配方；保持参考全局 batch 和学习率语义
- **hardware_target**：T3：单节点 4–8 张 24–48 GiB GPU，NCCL 数据并行；工程目标未实测
- **useful_output**：完整训练的可用分类器及完整验证预测

### 可选扩展：同一任务的变体

- **data**：相同数据和训练目标
- **hardware_target**：扩到 8 GPU 或多节点；固定有效 batch 与样本量，记录归约路径
- **not_new_task**：True

## GPU工作与预期资源形态

完整图像训练提供持续卷积和反向传播，加载/增强产生主机供数和 H2D 传输，优化器与 checkpoint 形成跨阶段状态。

## 资源标签（待画像验证）

- sustained_training
- convolution
- h2d_input_pipeline
- checkpoint_io
- optional_collectives

## 设备能力

- cuda
- fp32
- optional_amp
- optional_nccl

## 后端要求

- 兼容 PyTorch/TorchVision 和 GPU 驱动
- 可访问冻结的 ImageNet 图像存储
- 多 GPU 时支持 NCCL 与足够 /dev/shm

## 回放约束

- 模型训练由真实工具执行；agent 决策模型只回放。
- 固定数据顺序、随机种子、增强、精度和全局 batch；结束事件以训练器和 CUDA 完成为准。

## Builder需要实现的部分

- 构建有授权的输入快照并锁定源码 commit
- 封装分类交付目录与实际预测验证器
- 参考训练校准准确率容差和资源画像

## 与相关任务的边界

目标是整图单标签分类；与 B02 的多目标框索引、B03 的实例轮廓交付不同。

## 数据血缘

- imagenet_ilsvrc2012

## 任务范围与条件

- 完整训练是长任务；debug 不代表正式任务成本。
- ImageNet 分发和使用条件须单独确认；不能打包未授权图片。

## 来源记录

- [B_TORCHVISION] TorchVision classification reference — [来源](https://github.com/pytorch/vision/blob/main/references/classification/README.md)；检查位置：ResNet section; default training table; train.py entry point
- [B_ML_COMMONS] MLPerf Training reference workload catalogue — [来源](https://github.com/mlcommons/training)；检查位置：Historical v4.0 and v5.1 workload tables

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
