# GPUv1-B08 · 微调视频动作识别并输出片段目录

Fine-tune video action recognition and produce clip predictions

**组别**：视觉理解、分割与三维感知　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`ssv2_videomae_action_classifier`

**Workflow family**：`video_action_training`

## 任务目标

把预训练 VideoMAE 适配到 Something-Something V2 的动作类别，为完整验证视频输出 clip ID、类别概率与预测，并交付可处理新片段的模型和视频解码/采样配置。

## 具体来源工作负载

VideoMAE ViT-Base SSV2 source recipe: scripts/ssv2/videomae_vit_base_patch16_224_tubemasking_ratio_0.9_epoch_2400/finetune.sh; 174 classes; 16 frames; 30-epoch fine-tuning.

## 输入与配置

- dataset: Something-Something V2；split: 源 train.csv 和 val.csv 全量视频；preprocess: 源 240px 高度视频转换及原始片段身份
- model: VideoMAE ViT-Base；initial_weights: SSV2 2400-epoch masked-pretraining source checkpoint；finetune: 16 frames, 224 input, 174 classes, source 30 epochs

## 需要完成的工作

- 准备完整实际视频，检查解码长度与标注映射。
- 执行真实 GPU 微调，保留声明的帧采样与有效 batch。
- 对完整验证集执行源 multi-view 聚合，交付每片段概率和分类模型。

## 交付物

- fine-tuned checkpoint 与优化器状态
- val clip predictions/probabilities
- label_map.json 与采样配置
- 批量预测入口和验证报告

## 后续使用与状态

保留模型后处理预先声明的动作复核视频清单，交付易混动作对的实际预测和对应帧时间位置。

## 独立验收

- 核对原视频 ID 覆盖和 174 类概率维度、有限性与归一化。
- 独立按固定 multi-view 规则聚合预测并重算 top-k，参考运行校准容差。
- 检查真实视频解码和不同时间帧，拒绝把静态帧复制成整段。

## 应拒绝的失败方式

- 用单张静态帧重复填满视频
- 删除无法正确处理的 clip
- 把标签抄成 one-hot 概率
- 不同后端采用不同 test crop/segment 数

## 规模配方

### Debug：仅调通

- **data**：固定数百个真实视频的短调试清单
- **schedule**：短微调仅检查解码、label 和 checkpoint

### Reference large：正式生产规模

- **data**：完整 SSV2 源 train/val 视频清单
- **model_config**：ViT-Base 16-frame/224，30-epoch fine-tuning；复用现成预训练 encoder
- **hardware_target**：T3：8 张 40–80 GiB GPU；源脚本为 64 GPU，8-GPU 适配保持有效 batch 并重新校准；未实测
- **useful_output**：完整动作分类模型与全部验证片段预测

### 可选扩展：同一任务的变体

- **data**：相同视频和 fine-tune 目标
- **hardware_target**：具备资源时按源 64-GPU 配置执行；记录跨节点通信，仍为同一 task
- **not_new_task**：True

## GPU工作与预期资源形态

时空 attention、视频解码、帧采样、反向传播和多视角验证构成长时间 GPU 工作与 CPU/GPU 管线交叠。

## 资源标签（待画像验证）

- video_training
- temporal_attention
- decode_pipeline
- checkpoint_io
- collectives

## 设备能力

- cuda
- fp32_or_frozen_amp
- nccl
- source_deepspeed_if_selected

## 后端要求

- 视频解码库及源格式支持
- 大视频数据存储
- 多 GPU 通信和 launcher

## 回放约束

- 视频微调是真实任务侧模型训练。
- 所有采样帧和数据顺序由 manifest/seed 冻结；录制响应等待不替代异步训练完成。

## Builder需要实现的部分

- 锁定预训练 checkpoint、视频清单和解码版本
- 实现 8-GPU 等效配方并校准
- 封装 clip-level oracle 与资源分阶段测量

## 与相关任务的边界

学习人与物体动作的时间变化，既非静态分类也非视频生成；与 C 组生成工作无重叠。

## 数据血缘

- something_something_v2

## 任务范围与条件

- 源 fine-tune 的 64-GPU 示例不能直接声称适用于小机器；适配必须实测。
- SSV2 数据访问条件需要确认；不依赖现场下载可变视频。

## 来源记录

- [B_VIDEOMAE] VideoMAE Something-Something V2 fine-tuning recipe — [来源](https://github.com/MCG-NJU/VideoMAE/blob/main/scripts/ssv2/videomae_vit_base_patch16_224_tubemasking_ratio_0.9_epoch_2400/finetune.sh)；检查位置：ViT-Base SSV2 fine-tuning shell script
- [B_VIDEOMAE_DATA] VideoMAE dataset preparation — [来源](https://github.com/MCG-NJU/VideoMAE/blob/main/DATASET.md)；检查位置：Something-Something V2 preparation and CSV annotations

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
