# GPUv1-B10 · 训练户外米制深度模型并导出三维点云

Adapt outdoor metric depth and export geometry

**组别**：视觉理解、分割与三维感知　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`vkitti2_depthanything_outdoor_metric`

**Workflow family**：`metric_depth_adaptation`

## 任务目标

使用 Virtual KITTI 2 的真实渲染 RGB/深度数据适配户外米制深度模型，并在声明的真实 KITTI 验证图像上交付以米为单位的深度图；对指定图像结合相机内参导出可读取点云。

## 具体来源工作负载

Depth Anything V2 metric_depth/train.py --dataset vkitti --encoder vitl; dataset/splits/vkitti2/train.txt and dataset/splits/kitti/val.txt; 40-epoch default.

## 输入与配置

- dataset: Virtual KITTI 2；split: 源 dataset/splits/vkitti2/train.txt 的完整训练清单；assets: 对应 RGB 与米制深度、单位转换规则
- validation: KITTI；split: 源 dataset/splits/kitti/val.txt；assets: RGB、有效深度 mask、标定
- model: Depth Anything V2 ViT-L pretrained encoder + DPT depth head；training: 518 input; 40 source-default epochs; outdoor max_depth=80m

## 需要完成的工作

- 核对 VKITTI2 深度单位、有效区域和源划分，不将真实 KITTI 验证标签用于训练。
- 按源 metric-depth 配方训练 encoder/head 并保留模型/优化器状态。
- 对完整 KITTI 验证清单预测米制深度，按真实内参把指定结果投影为点云。

## 交付物

- metric-depth checkpoint 与训练配置
- 每图 float depth 数组和几何 metadata
- 声明图像的 PLY 点云
- 独立推理脚本、深度评测和投影报告

## 后续使用与状态

用已保存模型处理新的已声明户外帧清单，交付深度及按距离分层的几何统计；复用模型和固定内参规则。

## 独立验收

- 检查全验证覆盖、深度单位、有限数值、有效 mask 和原图对齐。
- 依据源 eval_depth 逻辑从实际预测重算误差，容差由参考训练校准。
- 独立将抽样深度与内参投影，核对点云坐标及对应像素。

## 应拒绝的失败方式

- 输出归一化伪彩色图却声称米制深度
- 把室内 20m 截断用到户外
- 依赖验证标签逐图缩放预测
- 点云使用任意未声明焦距

## 规模配方

### Debug：仅调通

- **data**：小批真实 VKITTI2 训练帧与 KITTI 验证帧
- **use**：单位、mask、投影和 checkpoint 调试

### Reference large：正式生产规模

- **data**：完整源 VKITTI2 train.txt 与完整 KITTI val.txt
- **model_config**：ViT-L metric depth；518 crop、40 epochs、户外 80m；source split frozen
- **hardware_target**：T3：4–8 张 40–80 GiB GPU 或经校准单张 80 GiB 方案；未实测
- **useful_output**：户外米制模型、完整验证深度图及几何产物

### 可选扩展：同一任务的变体

- **data**：更多完整 VKITTI2 场景须作为同一任务的声明规模实例，保持源 train/val 隔离
- **hardware_target**：固定有效 batch 后扩展数据并行；不增加任务计数
- **not_new_task**：True

## GPU工作与预期资源形态

较大视觉 encoder 的高分辨率微调提供持续 GPU 计算和激活显存，稠密浮点深度图产生实际 D2H 与空间产物写入。

## 资源标签（待画像验证）

- vision_transformer_training
- dense_float_output
- activation_memory
- geometry_export

## 设备能力

- cuda
- fp32_or_frozen_amp
- optional_nccl

## 后端要求

- Depth Anything V2 GPU 训练依赖
- VKITTI2/KITTI 数据与相机参数
- 能够持有训练状态和批量深度输出

## 回放约束

- 任务侧视觉模型训练/推理真实执行，agent LLM 不参与深度计算。
- 固定 depth units、resize、mask 和有效相机内参；本轮路径只做绑定。

## Builder需要实现的部分

- 锁定源 split 清单和 ViT-L encoder
- 构建 outdoor 配置与几何输出验证器
- 补足应用 checkpoint 的保存/恢复状态并校准大规模训练

## 与相关任务的边界

预测有物理单位的连续几何量并导出点云，区别于 B04 类别地图、B06 检测框和生成式 3D 工作。

## 数据血缘

- virtual_kitti2_and_kitti

## 任务范围与条件

- VKITTI2 为 CC BY-NC-SA 3.0 非商业用途数据。
- 源 outdoor 训练使用合成 VKITTI2、验证使用真实 KITTI；不能误写成在 KITTI 标签上训练。

## 来源记录

- [B_DEPTHANYTHING] Depth Anything V2 metric depth — [来源](https://github.com/DepthAnything/Depth-Anything-V2/blob/main/metric_depth/README.md)；检查位置：Metric depth models; training; point-cloud export
- [B_DEPTHANYTHING_TRAIN] Depth Anything V2 metric training code — [来源](https://github.com/DepthAnything/Depth-Anything-V2/blob/main/metric_depth/train.py)；检查位置：Argument defaults and vkitti/KITTI train-validation mapping
- [B_VKITTI2] Virtual KITTI 2 dataset — [来源](https://europe.naverlabs.com/proxy-virtual-worlds-vkitti-2/)；检查位置：Dataset description; Terms of Use

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
