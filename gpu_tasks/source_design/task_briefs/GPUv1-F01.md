# GPUv1-F01 · 从宇宙密度体数据训练参数回归模型

Train a cosmological-parameter regressor from density volumes

**组别**：科学机器学习与物理计算　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`cosmoflow_4parameter_regression`

**Workflow family**：`cosmological_parameter_estimation`

## 任务目标

为给定宇宙密度体数据建立四参数回归模型，交付可重新加载的模型、留出集预测和逐参数误差表；后续能够对新的模拟体输出相同语义的参数。

## 具体来源工作负载

MLCommons hpc/cosmoflow；cosmoUniverse_2019_05_4parE_tf_v2；128×128×128×4真实模拟裁块。

## 输入与配置

- 官方TFRecord v2训练/验证/测试划分及模拟参数标签
- 官方CosmoFlow TensorFlow/Keras模型与规范化配置
- 固定源模拟ID划分清单；同一模拟的裁块不得跨train/validation泄漏

## 需要完成的工作

- 核对四通道含义、目标列及归一化
- 在真实训练数据上完成声明训练阶段并保存权重、优化器和数据进度
- 对留出模拟体计算四参数预测和误差，导出独立推理入口

## 交付物

- model/及可加载检查点
- predictions.parquet，含source_simulation_id和四个目标
- metrics.json与输入/配置hash

## 后续使用与状态

重新加载所得模型，为此前未执行推理的同源测试模拟生成预测；保留模型和数据缓存的真实生命周期。

## 独立验收

- 检查模型可以加载并对私有留出体真实运行
- 重算逐参数MAE及预测行覆盖；容差从固定参考训练校准
- 验证训练使用声明样本、没有读取隐藏标签；训练完成度单独记录

## 应拒绝的失败方式

- 仅复制目标均值或原始标签
- 用官方179MB小样本充当正式规模
- 重复同一体或填充零张量提高设备占用

## 规模配方

### Debug：仅调通

- **workload**：官方small包32训练/32验证，仅检查流水线。

### Reference large：正式生产规模

- **data**：v2中按源模拟ID做hash排序，选出包含至少32768个不同训练裁块和4096个验证裁块的完整模拟组；冻结实际ID，保持128^3×4。
- **work**：完成一次预声明的训练阶段并给出完整验证预测；用上游收敛曲线在参考机确定固定更新预算，随后所有后端冻结该预算，不按目标机墙钟截断。
- **hardware_target**：T3：4×80GiB GPU，TensorFlow/Horovod all-reduce；为工程起始目标。

### 可选扩展：同一任务的变体

- **workload**：使用官方完整v2 train/val/test与8 GPU；完整MLPerf合规运行另立scenario，不把派生子集结果报为MLPerf分数。

## GPU工作与预期资源形态

3D卷积的真实体素激活、梯度及数据搬运提供持续设备计算和显存工作集；原始大数据还使读取与GPU计算交叠。

## 资源标签（待画像验证）

- sustained_training
- 3d_activations
- host_to_device
- dataset_io
- collectives
- checkpoint_state

## 设备能力

- CUDA TensorFlow
- supported mixed precision
- NCCL/Horovod for multi-GPU

## 后端要求

- 可分配4个可见GPU的参考配置
- 同机足够CPU/RAM和版本化TFRecord存储
- 固定rank/GPU映射及共享内存

## 回放约束

- 训练计算真实执行；只替换决策LLM输出与等待
- dataset shard与实际更新次数冻结；不能每个后端各自按时间预算结束

## Builder需要实现的部分

- 下载并hash固定v2数据与代码revision
- 构造不泄漏的源模拟组清单
- 校准模型质量与固定更新预算
- 实现模型重载与预测验证器

## 与相关任务的边界

目标是从三维宇宙密度场估计物理参数，与天气像素分类及流场时间演化的输入语义和产物不同。

## 数据血缘

- CosmoFlow/cosmoUniverse_2019_05_4parE_tf_v2
- MLPerf-HPC/CosmoFlow

## 任务范围与条件

- 较大的原始数据准备成本
- 派生训练阶段不等于官方完整MLPerf收敛协议
- 硬件需求和资源强度尚待画像

## 来源记录

- [F_MLPERF_HPC] MLPerf Training: HPC — [来源](https://mlcommons.org/benchmarks/training-hpc/)；检查位置：Benchmarks table; retirement notice
- [F_COSMOFLOW] CosmoFlow TensorFlow Keras reference — [来源](https://github.com/mlcommons/hpc/blob/main/cosmoflow/README.md)；检查位置：README Datasets; raw file retrieved and read with urllib

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
