# GPUv1-B06 · 训练驾驶场景三维目标检测并交付空间框

Train driving-scene 3D object detection

**组别**：视觉理解、分割与三维感知　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`nuscenes_centerpoint_detection`

**Workflow family**：`lidar_3d_detection_training`

## 任务目标

从 nuScenes 多次 LiDAR 扫描训练三维目标检测器，为完整验证场景交付包含位置、尺寸、朝向和速度的物体框，能够按场景和时间戳查询检测结果。

## 具体来源工作负载

MMDetection3D CenterPoint configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py; nuScenes v1.0-trainval.

## 输入与配置

- dataset: nuScenes v1.0-trainval；split: official train and val scenes；assets: samples/sweeps、标定、ego pose、scene/sample metadata
- config: centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py；schedule: source 20 epochs

## 需要完成的工作

- 构建源格式数据索引，保留扫帧时间和坐标转换。
- 按源配置训练 CenterPoint 并保存优化器/模型状态。
- 对完整验证场景执行 3D 检测，转换到 nuScenes 输出格式并生成时间索引。

## 交付物

- CenterPoint checkpoint
- nuScenes detection JSON 与场景查询索引
- 有效配置和转换程序
- 重算检测指标与数据清单

## 后续使用与状态

用既有检测结果追查指定时段的物体空间轨迹，并用保存模型重新处理预先选定的完整验证场景，核对 token 和坐标一致性。

## 独立验收

- 使用 nuScenes 格式检查 sample token、类别、translation、rotation、velocity 的合法性和覆盖。
- 从真实输出重算源检测指标，容差由参考运行校准。
- 抽样进行全局/车体/LiDAR 坐标往返检查，重推理选定场景。

## 应拒绝的失败方式

- 把局部坐标误当全局坐标
- 丢失 sweep/time 对齐
- 只输出二维框
- 复制 GT annotation 或跳过复杂场景

## 规模配方

### Debug：仅调通

- **data**：nuScenes mini 的完整场景
- **schedule**：只用于数据与 CUDA 稀疏算子调试

### Reference large：正式生产规模

- **data**：完整 nuScenes v1.0-trainval 的源 train/val 场景与声明 sweeps
- **model_config**：0.075 voxel CenterPoint；20-epoch 源配置
- **hardware_target**：T3：8 张 24–48 GiB GPU；NCCL 数据并行和 CUDA 稀疏算子；未实测
- **useful_output**：真实训练模型与全验证空间框

### 可选扩展：同一任务的变体

- **data**：同一场景全集
- **hardware_target**：2–8 GPU 适配需固定有效 batch/计划，保持场景分片语义
- **not_new_task**：True

## GPU工作与预期资源形态

非均匀点云、体素化、稀疏卷积、反向传播和多扫帧供数产生区别于稠密图像的 GPU 和主机数据压力。

## 资源标签（待画像验证）

- sparse_3d_training
- voxelization
- multi_sweep_io
- optional_collectives

## 设备能力

- cuda
- sparse_convolution_extensions
- nccl_for_ddp

## 后端要求

- MMDetection3D/MMCV/spconv 兼容构建
- nuScenes 完整 sweep 数据
- 足够 host RAM 与数据加载进程支持

## 回放约束

- 样本 token 稳定；本轮 worker/通信端口动态绑定。
- 冻结版本中的坐标约定，跨后端不得切换不同坐标重构版本。

## Builder需要实现的部分

- 锁定 config 及父配置、nuScenes split
- 构建空间输出 oracle
- 封装训练/预测并测正式画像

## 与相关任务的边界

学习具有朝向与速度的三维对象；与 B07 每个 LiDAR 点的语义赋值不同。

## 数据血缘

- nuscenes

## 任务范围与条件

- CUDA 稀疏算子和编译 ABI 是实际 backend 能力要求。
- mini 子集不能算正式 large。

## 来源记录

- [B_CENTERPOINT] MMDetection3D CenterPoint model zoo — [来源](https://github.com/open-mmlab/mmdetection3d/blob/main/configs/centerpoint/README.md)；检查位置：nuScenes configs/checkpoints; point sweeps and evaluation
- [B_CENTERPOINT_CONFIG] nuScenes CenterPoint voxel config — [来源](https://github.com/open-mmlab/mmdetection3d/blob/main/configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py)；检查位置：0.075 voxel, circle-NMS, 20-epoch config

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
