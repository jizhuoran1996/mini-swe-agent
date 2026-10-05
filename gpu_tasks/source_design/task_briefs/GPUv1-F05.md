# GPUv1-F05 · 推进大型膜蛋白体系并交付动力学分析

Advance a membrane-protein simulation and deliver trajectory analysis

**组别**：科学机器学习与物理计算　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`hecbiosim_hegfr_gromacs_md`

**Workflow family**：`biomolecular_molecular_dynamics`

## 任务目标

从给定膜蛋白平衡状态推进1ns分子动力学，交付完整续跑检查点、按规定间隔采样的轨迹，以及温度、能量和蛋白结构偏移分析。

## 具体来源工作负载

HECBioSim GROMACS 465K hEGFR Dimer (1IVO/1NQL)，465399原子，官方gromacs.tar.xz输入。

## 输入与配置

- HECBioSim 465K hEGFR官方TPR和对应体系
- 固定GROMACS构建、力场及精度
- 与源TPR一致的温压/约束/PME设定；采样间隔明确写入recipe

## 需要完成的工作

- 解析TPR并核对原子数与物理时间步
- 使用GPU支持路径推进目标物理时间并保存真实checkpoint
- 读取本次轨迹生成温度/能量/RMSD时间序列

## 交付物

- 最终checkpoint及可续跑输入
- trajectory.xtc与energy.edr
- analysis.csv、选择组和方法说明

## 后续使用与状态

使用本次checkpoint继续0.1ns，确认模拟时间和状态连续；不能从初始TPR重新开始。

## 独立验收

- 用GROMACS工具重读轨迹和能量文件，核对原子数/时间覆盖/帧间隔
- 重算分析指标并检查物理量有限；容差以相同设定参考积分校准
- 检查continuation从实际checkpoint时间接续，长轨迹不要求逐bit坐标相等

## 应拒绝的失败方式

- 只跑测速步数而未到1ns
- 用复制帧填充轨迹
- 关闭主要相互作用或改步长缩减工作
- 用性能日志代替结果文件

## 规模配方

### Debug：仅调通

- **workload**：同一465399原子体系短100步，仅检查GPU/TPR兼容性。

### Reference large：正式生产规模

- **data**：完整465399原子hEGFR dimer，保留全部脂质、水和离子，不裁剪为小蛋白。
- **work**：1ns真实MD、声明频率的轨迹/能量输出及0.1ns有状态续跑；从TPR的dt计算并冻结步数。
- **hardware_target**：T1：1×24–48GiB GPU与足够宿主CPU；是否部分PME留在CPU先固定。

### 可选扩展：同一任务的变体

- **workload**：同一体系2–4 GPU域分解，或对官方更大hEGFR输入单独建立scale manifest；不能把它们算作新任务。

## GPU工作与预期资源形态

大原子系统持续邻域力计算、PME和积分，不依赖训练模型；GPU常驻原子状态和周期输出形成不同于深度学习的调度特征。

## 资源标签（待画像验证）

- sustained_simulation
- resident_particle_state
- cpu_gpu_split
- checkpoint_io
- periodic_output

## 设备能力

- GROMACS CUDA build
- GPU kernels supported by source TPR
- MPI if scale-out

## 后端要求

- 固定CPU/GPU任务映射
- 持久checkpoint和工作区
- GPU访问与相容驱动；多GPU时声明拓扑

## 回放约束

- 模拟进程持续执行，不能以sleep代替
- 暂停恢复只在应用checkpoint边界使用；不声称通用VM快照能保存CUDA上下文

## Builder需要实现的部分

- 绑定官方归档中实际文件和hash
- 验证TPR在选定GROMACS版本可读
- 形成能量与轨迹连续性oracle
- 校准CPU/GPU分工

## 与相关任务的边界

带膜蛋白的经典分子动力学时间积分，与蛋白折叠模型推理、催化结构弛豫和金属SNAP材料模型具有不同方程及产物。

## 数据血缘

- HECBioSim/GROMACS/465K-hEGFR-dimer
- PDB/1IVO+1NQL

## 任务范围与条件

- 1ns交付用于规定动力学过程，不足以断言蛋白达到长期平衡
- 混沌轨迹允许经过校准的统计容差
- 资料中的465K不可误写成465303等其他版本原子数

## 来源记录

- [F_HECBIOSIM] HECBioSim HPC Benchmarking Suite — [来源](https://www.hecbiosim.org/access-hpc/hpc-benchmarking-suite)；检查位置：465K hEGFR dimer; raw GROMACS input archive
- [F_GROMACS] Getting good performance from mdrun — [来源](https://manual.gromacs.org/current/user-guide/mdrun-performance.html)；检查位置：GPU configuration; GPU-resident mode; GPU task assignment

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
