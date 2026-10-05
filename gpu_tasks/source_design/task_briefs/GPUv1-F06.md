# GPUv1-F06 · 模拟金属晶体并分析有限温度结构稳定性

Simulate a metal crystal and analyze finite-temperature structure

**组别**：科学机器学习与物理计算　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`lammps_snap_ta_bcc_dynamics`

**Workflow family**：`atomistic_material_simulation`

## 任务目标

使用给定SNAP势推进有限温度BCC钽晶体，交付可续跑的原子状态、能量漂移和径向分布报告，确认计算期间的结构行为。

## 具体来源工作负载

LAMMPS examples/snap/in.snap.Ta06A；potentials/Ta06A.snap、Ta06A.snapcoeff、Ta06A.snapparam；Kokkos GPU。

## 输入与配置

- 官方BCC晶格生成规则及3.316Å晶格参数
- Ta06A SNAP+ZBL势文件和质量设定
- 冻结300K初始速度seed及周期边界；固定物理域尺寸

## 需要完成的工作

- 从官方晶格规则建立声明空间域并保存初态
- 通过Kokkos GPU进行NVE时间积分
- 输出规定频率的能量、原子轨迹和restart，计算RDF/结构统计

## 交付物

- initial.data和final.restart
- thermo.csv、trajectory文件和RDF结果
- 实际势/积分/邻域参数及构建信息

## 后续使用与状态

从final.restart接着积分5ps，再生成新增区间的统计；要求保留速度、盒和势配置。

## 独立验收

- 核对原子数、盒长、势文件hash及正确的单位/时间覆盖
- 在保存帧上独立重算RDF、能量和简单结构统计
- 能量漂移/初期力的数值容差基于固定参考确定；不用CPU/GPU长轨迹逐bit相等

## 应拒绝的失败方式

- 只生成晶格而不积分
- 用解析曲线替代本次RDF
- 删除SNAP或ZBL相互作用
- 反复复制轨迹帧或以空循环冒充物理时间

## 规模配方

### Debug：仅调通

- **workload**：官方nrep=4、100步示例，仅作构建检查。

### Reference large：正式生产规模

- **data**：按同一物理晶格规则建立32×32×32个BCC晶胞，共65536个相互作用的真实原子；固定密度/周期边界。
- **work**：沿官方0.5fs时间步推进50ps，即100000步，并完成5ps续跑；数据增大来自物理域，不能复制不相互作用的独立填充。
- **hardware_target**：T1：1×24–48GiB GPU，Kokkos CUDA；工作时长必须画像。

### 可选扩展：同一任务的变体

- **workload**：同一物理域2–8 GPU MPI域分解；若做有限尺寸分析可用64^3晶胞形成同ID规模实例，并保留物理解释。

## GPU工作与预期资源形态

SNAP多体描述符和原子邻域计算提供真实计算密集路径，粒子状态在GPU反复访问；域分解产生可控设备间通信。

## 资源标签（待画像验证）

- sustained_simulation
- many_body_potential
- resident_particle_state
- domain_decomposition
- checkpoint_state

## 设备能力

- LAMMPS ML-SNAP
- Kokkos CUDA with snap/kk and compatible hybrid styles
- MPI for scale-out

## 后端要求

- GPU架构匹配的LAMMPS构建
- 固定GPU-aware MPI或明确的host staging方案
- 实际restart/轨迹工作区

## 回放约束

- 冻结积分步数与势，不随目标GPU速度改工作量
- 多GPU时固定rank和逻辑设备映射，等待真实MPI与GPU完成

## Builder需要实现的部分

- 构建并验证SNAP+ZBL在选定Kokkos版本的设备执行
- 保存官方势文件与生成初态hash
- 实现restart、能量和RDF验证
- 验证50ps的参考时间/温度稳定性

## 与相关任务的边界

研究理想金属有限温度原子结构，使用机器学习多体势和周期晶格；与膜蛋白经典力场和吸附极小化目标不同。

## 数据血缘

- LAMMPS/examples/snap/in.snap.Ta06A
- LAMMPS/potentials/Ta06A

## 任务范围与条件

- 是从官方示例派生的有限尺寸材料任务，不是新实验材料发现
- 更长模拟和更大空间域需由物理问题解释
- 需确认全部目标样式有GPU实现，记录混合CPU路径

## 来源记录

- [F_LAMMPS_INPUT] LAMMPS SNAP tantalum example — [来源](https://github.com/lammps/lammps/blob/develop/examples/snap/in.snap.Ta06A)；检查位置：in.snap.Ta06A and potentials/Ta06A.snap; raw files retrieved and read
- [F_LAMMPS_SNAP] LAMMPS pair_style snap — [来源](https://docs.lammps.org/pair_snap.html)；检查位置：Ta06A example; accelerated styles
- [F_LAMMPS_KOKKOS] LAMMPS KOKKOS package — [来源](https://docs.lammps.org/Speed_kokkos.html)；检查位置：GPU execution and GPU-aware communication

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
