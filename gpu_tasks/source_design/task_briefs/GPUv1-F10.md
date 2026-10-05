# GPUv1-F10 · 预测三维湍流混合层并验证多步演化

Forecast a three-dimensional turbulent mixing layer

**组别**：科学机器学习与物理计算　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`thewell_trl3d_fno_rollout`

**Workflow family**：`astrophysical_flow_surrogate`

## 任务目标

为冷热气体三维湍流混合层建立下一时刻预测器，并在留出模拟上滚动预测后续状态，交付密度、压强、速度场及误差随时间变化的报告。

## 具体来源工作负载

The Well turbulent_radiative_layer_3D；官方FNO基线、真实train/valid/test及rollout评估。

## 输入与配置

- The Well turbulent_radiative_layer_3D完整数据：90条物理序列、101帧、256×128×128网格、约744.6GB
- 官方FNO模型/归一化/训练与数据划分
- 四帧历史输入和源数据冷却参数，真实目标场用于验证

## 需要完成的工作

- 按官方trajectory划分加载并保持全3D空间语义
- 完成规范训练阶段并保存FNO状态
- 在整个test split以真实历史启动多步rollout，导出体场和vRMSE及物理统计

## 交付物

- FNO检查点与normalization统计
- test_rollouts/含真实坐标和时间
- vRMSE曲线、密度/压强有限性及混合层统计

## 后续使用与状态

加载保存的最近4帧历史/预测状态继续自由rollout，并统计新增时间段；续报不得超过该源序列实际剩余真值范围。从最初4帧启动时总预测最多97步。使用未来真值作输入的teacher forcing与自由rollout必须明确区分。

## 独立验收

- 重载模型和3D体场，核对每条序列的网格/字段/时间
- 重算独立测试的一步误差和自由rollout误差，容差与固定参考训练预算绑定
- 验证没有跨轨迹泄漏或使用未来真值；物理异常和预测退化须如实报告
- 核对历史帧、预测起点和目标时间索引：101帧序列使用前4帧初始化时，可验证预测最多97步；禁止越过源horizon或把初始化帧计作新增预测。

## 应拒绝的失败方式

- 把3D体下采样为2D切片后声称同任务规模
- 只保存可视化图片
- 自由rollout实际每步偷偷读取真值
- 靠重复同一模拟补足数据量

## 规模配方

### Debug：仅调通

- **workload**：同一数据集的一条训练序列短时间窗口，仅用于格式和CUDA检查。

### Reference large：正式生产规模

- **data**：完整官方train/valid/test、原生256×128×128空间场；数据应预置本地而非每轮在线流。
- **work**：参考官方FNO配置完成校准的固定更新阶段，整个test split执行30步自由rollout并计算源vRMSE；官方12小时H100预算仅用于选定阶段，采集后改为冻结实际update/data-order，不按各后端墙钟改变工作。
- **hardware_target**：T2：1×80GiB GPU作为起始参考；使用官方可复现模型和显存策略。

### 可选扩展：同一任务的变体

- **workload**：2–8 GPU数据并行；时间扩展从源序列最初4帧作为历史启动，最多预测其余97帧，合计覆盖101个源时刻。若从更晚窗口开始，则按实际剩余帧数进一步缩短；不按冷却参数/随机种子另增task ID。

## GPU工作与预期资源形态

全3D物理体上的频域算子及多步状态预测形成大激活与持续设备计算，真实744.6GB数据源同时覆盖主机到GPU与存储供数。

## 资源标签（待画像验证）

- 3d_activations
- spectral_operator
- autoregressive_rollout
- dataset_io
- checkpoint_state

## 设备能力

- CUDA PyTorch
- FFT kernels
- official FNO/neuraloperator stack

## 后端要求

- 预置大体积HDF5数据与足够主机供数能力
- 固定3D模型/精度与归一化
- 输出和checkpoint的私有存储

## 回放约束

- 以真实CUDA完成事件和文件完成状态建立依赖
- 固定实际训练更新及rollout次数；来源的墙钟训练预算不直接作为后端可变工作量

## Builder需要实现的部分

- 固定官方数据划分/模型配置/代码revision
- 校准可交付训练阶段与数值质量
- 实现3D rollout重载和vRMSE验证
- 确认整个test split及输出空间预算

## 与相关任务的边界

问题是星际冷热气体混合层的三维时间演化，输出密度/压强/速度体；不同于全球大气预报、气候事件分类和车辆静态表面场。

## 数据血缘

- TheWell/turbulent_radiative_layer_3D
- Athena++/radiative-mixing-layer
- TheWell/FNO-baseline

## 任务范围与条件

- 原始数值模拟由CPU生成，任务中的FNO训练/预测是真实GPU工作；不能混淆两者
- 代理误差可能随rollout增长，不能以不稳定就删样本
- 需预置较大科学数据

## 来源记录

- [F_WELL_DATA] The Well: turbulent_radiative_layer_3D — [来源](https://polymathic-ai.org/the_well/datasets/turbulent_radiative_layer_3D/)；检查位置：About the data; physical variables; simulation suite
- [F_WELL_BASELINE] The Well benchmark models — [来源](https://polymathic-ai.org/the_well/benchmarks/)；检查位置：Baseline protocol; pretrained models; VRMSE and rollouts

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
