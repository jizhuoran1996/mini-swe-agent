# GPUv1-B09 · 训练单目标跟踪器并生成连续轨迹

Train a single-object tracker and export trajectories

**组别**：视觉理解、分割与三维感知　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`got10k_ostrack_single_object_tracking`

**Workflow family**：`visual_object_tracking`

## 任务目标

训练一个只依赖首帧目标框的视觉跟踪器，在完整验证序列上连续跟踪指定物体，交付每帧边框、置信度与可独立运行的模型。

## 具体来源工作负载

OSTrack official GOT-10k config vitb_384_mae_ce_32x4_got10k_ep100; MAE ViT-Base initialization; GOT-10k train and validation.

## 输入与配置

- dataset: GOT-10k；split: 官方 train/val；仅 train 参与训练；binding: 冻结每序列帧清单、初始化框和验证标签
- model: OSTrack ViT-B 384；config: vitb_384_mae_ce_32x4_got10k_ep100；initial_weights: MAE ViT-Base source weights

## 需要完成的工作

- 准备真实完整序列，区分首帧初始化和未来帧标注。
- 按 GOT-10k 专用 100-epoch 源配置训练并保存模型。
- 逐序列执行连续 GPU 跟踪，导出与帧一一对应的框与有效状态。

## 交付物

- OSTrack checkpoint 和配置
- 逐序列 boxes/confidence 文件
- 跟踪入口与初始化说明
- 完整验证覆盖及跟踪指标报告

## 后续使用与状态

使用持有的模型跟踪后续声明序列，或从合法首帧重新初始化某个长序列，输出完整轨迹并与原序列身份关联。

## 独立验收

- 检查每序列只使用首帧框初始化，输出长度与帧清单一致，坐标合法。
- 按验证标注重算 overlap/success 指标，数值容差经参考训练校准。
- 抽样重跑完整短序列，检查结果由实际状态推进产生。

## 应拒绝的失败方式

- 每帧用 ground-truth 框重新初始化
- 复制首帧框到所有帧
- 丢弃遮挡或出视野帧
- 使用未来帧标签训练或调整预测

## 规模配方

### Debug：仅调通

- **data**：固定少量完整真实训练/验证序列
- **use**：检查采样、初始化和持续跟踪状态

### Reference large：正式生产规模

- **data**：完整 GOT-10k source train 和 val；保留原始完整序列
- **model_config**：vitb_384_mae_ce_32x4_got10k_ep100，源 100 epochs
- **hardware_target**：T3：4 张 24–48 GiB GPU 的训练目标；推理可单 GPU 持有模型，未实测
- **useful_output**：跟踪模型与全验证序列轨迹

### 可选扩展：同一任务的变体

- **data**：官方 test 序列用于大规模结果导出，不依赖在线榜单评分
- **hardware_target**：2–8 GPU 按序列分配，保持单序列时间依赖
- **not_new_task**：True

## GPU工作与预期资源形态

训练包含大量真实模板/搜索帧对，推理保留目标模板和逐帧状态，覆盖长序列内的小 GPU 调用及模型驻留。

## 资源标签（待画像验证）

- video_tracking
- stateful_inference
- template_state
- training
- many_small_gpu_calls

## 设备能力

- cuda
- optional_nccl

## 后端要求

- OSTrack/ViT 环境与图像加载
- 完整视频帧目录
- 训练多进程环境

## 回放约束

- 序列内保持帧依赖，不能并行无状态替换每帧结果。
- 保存应用级 tracker 模板/状态并声明恢复契约；不假设可迁移 CUDA context。

## Builder需要实现的部分

- 获取 GOT-10k 输入并固定官方专用配置
- 封装 val 本地评测，避免依赖在线提交
- 记录状态驻留、逐帧 GPU 事件和 checkpoint

## 与相关任务的边界

输出同一目标跨时间的身份连续轨迹；与 B08 整段动作类别不同。

## 数据血缘

- got10k

## 任务范围与条件

- 此卡不把不同分辨率/训练轮数拆为更多任务。
- 模型/数据下载和上游旧依赖需先冻结。

## 来源记录

- [B_OSTRACK] OSTrack official implementation — [来源](https://github.com/botaoye/OSTrack)；检查位置：Training; GOT-10k evaluation with vitb_384_mae_ce_32x4_got10k_ep100

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
