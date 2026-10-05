# GPUv1-F02 · 建立大气河流与热带气旋识别模型

Build a climate-event segmentation model

**组别**：科学机器学习与物理计算　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`deepcam_cam5_teca_event_masks`

**Workflow family**：`climate_event_segmentation`

## 任务目标

将给定多变量气候模拟帧转换为背景、大气河流和热带气旋的空间标注，训练并交付可部署的分割模型及留出时段事件目录。

## 具体来源工作负载

MLCommons hpc/deepcam；CAM5 All-Hist的train/val/test、stats.h5和DeepCAM参考模型。

## 输入与配置

- CAM5+TECA HDF5帧，保持768×1152×16的原始空间/通道语义
- 官方三类标签与stats.h5
- 按连续模拟时段划分的训练与留出清单

## 需要完成的工作

- 核对通道统计和类别映射
- 训练源模型并保存可重新加载的checkpoint
- 为留出时段生成逐像素mask，并归纳事件面积与时间索引

## 交付物

- segmentation-checkpoint/
- masks/和event_catalog.parquet
- 逐类IoU/混淆矩阵及完整输入清单

## 后续使用与状态

用保存的模型处理新时段，追加事件目录并校验旧时段结果和索引保持一致。

## 独立验收

- 独立加载checkpoint并重算私有留出帧mask
- 校验mask的空间shape、类别、时间ID及完整覆盖
- 从真实预测重算逐类IoU，固定参考预算对应的质量容差另行校准

## 应拒绝的失败方式

- 只生成背景mask
- 忽略稀少事件类
- 把全分辨率输入缩成小图后仍宣称原规模
- 把验证帧用于训练

## 规模配方

### Debug：仅调通

- **workload**：官方All-Hist中固定8帧，原分辨率，仅用于构建检查。

### Reference large：正式生产规模

- **data**：从官方train按连续时间块确定4096个不同训练帧，val确定1024帧；按时间块分隔，冻结源文件名与hash。
- **work**：采用官方DeepCAM模型和训练规则，在参考机校准可交付阶段的更新预算，随后固定更新数并完整生成1024帧验证mask；不使用任意重复帧制造压力。
- **hardware_target**：T3：4×80GiB GPU；PyTorch分布式训练/NCCL。

### 可选扩展：同一任务的变体

- **workload**：官方完整All-Hist划分，8 GPU训练或独立并行推理；资源预算变化仍为同一任务。

## GPU工作与预期资源形态

大幅面多通道真实气候场产生卷积激活与梯度驻留；类别预测和持续数据加载同时压GPU与主机数据通道。

## 资源标签（待画像验证）

- sustained_training
- large_dense_tensors
- host_to_device
- dataset_io
- collectives

## 设备能力

- CUDA PyTorch
- distributed training
- NCCL for multi-GPU

## 后端要求

- GPU设备直通或受支持的CUDA隔离
- HDF5数据和固定规范化统计
- 足够的DataLoader共享内存与文件描述符

## 回放约束

- 冻结实际训练操作数及数据顺序
- checkpoint和mask真正生成；验证器不代替agent完成GPU分割

## Builder需要实现的部分

- 固定All-Hist版本及时间块ID
- 校准训练预算与事件类oracle
- 实现mask/事件目录复核
- 分开记录HDF5读取和GPU活动

## 与相关任务的边界

科学目标是极端天气事件的空间定位；不是全球数值天气预测或区域降尺度，也不是换一组图像标签的CV模型大小变体。

## 数据血缘

- CAM5/All-Hist
- TECA/event-labels
- MLPerf-HPC/DeepCAM

## 任务范围与条件

- 官方完整数据体量大
- 标签来自模拟和TECA，不等同人类观测真值
- 不把缩减协议称为官方MLPerf结果

## 来源记录

- [F_MLPERF_HPC] MLPerf Training: HPC — [来源](https://mlcommons.org/benchmarks/training-hpc/)；检查位置：Benchmarks table; retirement notice
- [F_DEEPCAM] DeepCAM climate segmentation reference — [来源](https://github.com/mlcommons/hpc/blob/main/deepcam/README.md)；检查位置：README Dataset; src/deepCam/run_scripts/run_training.sh; raw files retrieved and read

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
