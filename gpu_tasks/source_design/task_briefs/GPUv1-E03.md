# GPUv1-E03 · 训练完整 HIGGS 事件分类模型

Train a full-data HIGGS event classifier

**组别**：GPU数据、向量与图计算　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`higgs_signal_classifier`

**Workflow family**：`gpu_boosted_tree_learning`

## 任务目标

使用完整 HIGGS 数据训练可重载的信号/背景分类器，提交冻结测试集的逐事件概率及特征说明，支持后续新批次分类。

## 具体来源工作负载

UCI HIGGS 11,000,000 rows; XGBoost CUDA histogram training and QuantileDMatrix

## 输入与配置

- 官方 HIGGS.csv.gz 全量 28 特征及标签
- 原始顺序前 10M 训练、中间 0.5M 验证、最后 0.5M 保留为官方测试尾部
- 固定 CUDA hist 训练配方：初版 max_depth=8、eta=0.1、最多 500 轮，验证集 early stopping=30；正式参数由参考运行冻结

## 需要完成的工作

- 验证列与标签并避免测试集参与拟合
- 在 GPU 构造量化数据并执行完整训练
- 保存 Booster、特征顺序及逐样本测试预测，再重新加载预测

## 交付物

- higgs_model.ubj
- test_probabilities.parquet
- feature_schema.json、training_manifest.json

## 后续使用与状态

用已加载模型对固定第二批事件产生概率和阈值分组统计，保留模型状态供查询。

## 独立验收

- 独立重载 Booster 对隐藏固定事件产生一致概率
- ROC-AUC/logloss 与冻结参考范围比较，容差和最低质量在采集前校准
- 测试行 ID 覆盖全部 0.5M、概率有限且取值有效
- GPU 准入确认训练与预测 kernel，而非仅 CUDA 初始化

## 应拒绝的失败方式

- 测试泄漏
- 仅输出类别先验或训练日志
- 只训练前几批
- 列错位或标签被当作输入

## 规模配方

### Debug：仅调通

- **workload**：100K 固定训练行加独立 10K 验证行，仅调试
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：原生全部 11M 事件，10M 训练与各 0.5M 验证/测试；有效 early stopping 后交付模型
- **proposed_hardware_tier**：T1：单 24–48GiB CUDA GPU；这是工程目标，不声称需要占满显存
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：同一全量数据使用官方 Dask/XGBoost 多 GPU 路径；不通过复制样本扩容
- **separate_task_id**：False

## GPU工作与预期资源形态

大规模量化、梯度/直方图构造与树学习提供真实持续 GPU 工作；需求可能偏计算而非极大显存，画像后分类。

## 资源标签（待画像验证）

- gpu_tree_training
- gpu_histograms
- resident_dataset
- host_device_transfer

## 设备能力

- CUDA
- XGBoost GPU hist

## 后端要求

- 固定 XGBoost/CUDA 版本；禁止静默 device=cpu 回退
- 保留训练进程、模型与量化数据的生命周期范围

## 回放约束

- 固定数据行序、切分、模型 seed、early-stopping 规则
- LLM 回放不替代实际树训练
- GPU 完成和模型写入完成后才能进入后续推理

## Builder需要实现的部分

- 下载并哈希 UCI 全量数据
- 实现数据切分/训练/重载 CLI
- 先校准功能质量和正式训练时长，再准入

## 与相关任务的边界

与 E04 属于 boosted-tree 家族，但物理事件分类与交通回归有不同标签、数据和验证；F 组若已有相同 HIGGS 目标必须合并。

## 数据血缘

- uci_higgs_11m

## 任务范围与条件

- 此输入较大但可能不属于高显存类；不得为了显存占用增大无用途的树深或复制数据
- 训练超参数是本包拟定配置，尚未测量

## 来源记录

- [E_HIGGS] UCI HIGGS dataset — [来源](https://archive.ics.uci.edu/dataset/280/higgs)；检查位置：11M rows, 28 features, binary event classification, last 500K test examples
- [E_XGB] XGBoost GPU support — [来源](https://xgboost.readthedocs.io/en/stable/gpu/index.html)；检查位置：device=cuda, tree_method=hist, QuantileDMatrix, GPU prediction and distributed execution

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
