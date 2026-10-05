# GPUv1-F04 · 完成催化吸附初态弛豫与能量排序

Relax catalyst adsorption structures and rank their energies

**组别**：科学机器学习与物理计算　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`oc20_equiformer_is2rs_relaxation`

**Workflow family**：`adsorption_structure_relaxation`

## 任务目标

对给定催化表面吸附初态执行机器学习势弛豫，交付最终结构、能量、最大自由原子力与收敛状态，并按声明分组排序。

## 具体来源工作负载

OC20 IS2RE验证初态；EquiformerV2 153M All+MD检查点；main_oc20.py弛豫路径。

## 输入与配置

- OC20 IS2RE val_id、val_ood_ads、val_ood_cat、val_ood_both中的真实初态
- 官方EquiformerV2 153M All+MD权重和配置
- 保留sid、原子标签、周期盒、固定原子约束及能量参考

## 需要完成的工作

- 加载同一势模型并校验单位与固定原子
- 以固定优化器、力阈值和最大步数运行实际弛豫
- 保存每个体系的最终几何与轨迹摘要；失败和未收敛均保留

## 交付物

- relaxed_structures.extxyz
- energies.parquet含sid/step/convergence
- 按吸附体系语义分组的排名与运行配置

## 后续使用与状态

从已保存的未收敛状态继续到声明总步数，并更新对应行；已经收敛的结构不能被重新随机初始化。

## 独立验收

- 重载最终几何，在GPU上重算能量/力并检查单位和固定原子
- 核对每个sid输出完整、原子种类和周期边界未改变
- 收敛阈值及参考数值容差先校准；未收敛状态明确记录，不靠删行改善指标

## 应拒绝的失败方式

- 复制初态并伪造能量
- 用标签能量代替势计算
- 移动固定底层原子
- 只保留容易收敛的体系

## 规模配方

### Debug：仅调通

- **workload**：每个验证分区各2个真实sid。

### Reference large：正式生产规模

- **data**：四个官方验证分区各取SHA256(sid)排序最前128个，共512个不同体系；冻结sid及结构hash。
- **work**：所有512个体系执行固定优化器的真实力/能量计算及弛豫；物理停止准则和总步数上限写入manifest。
- **hardware_target**：T2：1×80GiB GPU；可按原子数分批，但不改变体系。

### 可选扩展：同一任务的变体

- **workload**：2–8 GPU按体系分片，扩大到四个完整验证分区；不需把全153M模型预训练放入任务。

## GPU工作与预期资源形态

等变图网络在不断变化的真实原子邻域上重复计算力，产生持续GPU推理、图重建和动态工作集。

## 资源标签（待画像验证）

- iterative_inference
- dynamic_graph
- variable_shape
- model_residency
- cpu_gpu_pipeline

## 设备能力

- CUDA PyTorch/PyG
- compatible EquiformerV2 kernels

## 后端要求

- 固定兼容旧OCP/Equiformer代码栈
- 保存轨迹和最终状态的私有工作区
- 可见GPU以及足够CPU用于邻域和优化器

## 回放约束

- 固定本轮逻辑sid和优化器；实际弛豫完成条件决定真实工作
- agent等待期间模型状态若保留，必须计显存；应用state文件不是GPU上下文快照

## Builder需要实现的部分

- 固定下载到的OC20 split和权重hash
- 实施真实force oracle
- 校准数值差异与收敛分类
- 验证旧配置和现代驱动的兼容性

## 与相关任务的边界

任务求的是周期催化表面的几何极小值和能量排序，不是泛化图分类、蛋白结构预测或长时间分子动力学。

## 数据血缘

- OC20/IS2RE/val_id,val_ood_ads,val_ood_cat,val_ood_both
- EquiformerV2/153M/All+MD

## 任务范围与条件

- ML势近似DFT，排序不等于实验结论
- 模型已经使用All+MD训练，适合作系统回放，不能据此声称未知分布科学泛化
- 全验证集昂贵，reference明确是固定子集

## 来源记录

- [F_OC20] OC20 dataset and downloads — [来源](https://facebookresearch.github.io/fairchem/oc20/)；检查位置：S2EF and IS2RE split download instructions
- [F_EQUIFORMER] EquiformerV2 — [来源](https://github.com/atomicarchitects/equiformer_v2)；检查位置：README Checkpoints; File Structure; main_oc20.py

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
