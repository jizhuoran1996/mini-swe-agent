# GPUv1-E09 · 训练异构学术图的主题分类器

Train a heterogeneous academic graph topic classifier

**组别**：GPU数据、向量与图计算　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`igbh_paper_topic_classifier`

**Workflow family**：`gpu_gnn_learning`

## 任务目标

在论文、作者等多类型关系构成的学术图上训练论文主题分类器，交付可恢复模型和按原始paper ID组织的预测，让后续查询能继续使用模型与图特征。

## 具体来源工作负载

IGBH-large real heterogeneous graph/features; MLPerf retired_benchmarks/rgat/train_rgnn_multi_gpu.py model=rgat, 3 layers, hidden=512, 4 heads, fan_out=15,10,5

## 输入与配置

- IGBH-large 原生异构数据集与真实1024维特征，禁止随机替代
- 2983类标签；官方split_seeds.py按固定seed生成的训练/验证ID，随后冻结
- MLPerf参考关系GAT模型及采样配置；layout=CSC、use_fp16；其2个完整epoch上限作为派生配方起点

## 需要完成的工作

- 核对各节点类型、关系和特征映射，完成声明的图布局/特征精度准备
- 按GLT异构采样/多GPU训练路径执行完整训练
- 保存模型/优化器/采样状态，导出验证ID预测并重载验证

## 交付物

- rgat_checkpoint.pt
- paper_predictions.parquet
- graph_feature_manifest.json
- inference.py

## 后续使用与状态

重载提交模型，对已声明的一组未查询论文执行主题预测，并保留实际图特征worker。

## 独立验收

- 仅训练掩码参与梯度，关系/特征非随机替代
- 模型重载后预测与参考容差及准确率范围一致
- 全量保留集paper ID覆盖，类别和数值有效
- 恢复训练状态时采样器和optimizer非空且对应已训练步数

## 应拒绝的失败方式

- 用随机node features替代真实数据
- 只训练tiny却标为large
- 移除关系退化成只看标签的分类器
- 缓存官方预测当作模型结果

## 规模配方

### Debug：仅调通

- **workload**：IGBH-tiny，真实特征，用来验证数据/关系/训练恢复路径
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：IGBH-large 完整原生图；使用参考脚本的3层RGAT和2个完整epoch上限，验证停止目标由该规模参考校准；不截成几批
- **proposed_hardware_tier**：T3：4×80GiB GPU与充足主机RAM/NVMe；大/全量资产存储超过500GB，容量需预检
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：IGBH-Full作为advanced扩展；原生数据约2.2TB，2–8GPU分布式采样/特征缓存，主机RAM另做容量预检；不是默认MLPerf合规运行
- **separate_task_id**：False

## GPU工作与预期资源形态

关系采样、随机特征读取、稀疏聚合、dense层及梯度通信同时存在，大特征状态常在主机和GPU之间移动。

## 资源标签（待画像验证）

- gpu_gnn_training
- sparse_dense_mixed
- host_device_transfer
- gpu_collectives
- large_feature_state

## 设备能力

- CUDA
- PyTorch
- GraphLearn-Torch GPU sampling

## 后端要求

- 固定可运行GLT/PyTorch/CUDA版本并按设备架构构建
- 多GPU采样/训练资源与特征存储位置明示；pin_feature的主机锁页内存计入预算
- 数据使用已更新的真实特征文件

## 回放约束

- 冻结采样seed、图版本、mask和训练停止条件
- LLM等待期间真实采样worker与特征缓存保留
- 应用checkpoint恢复独立于GPU虚拟化snapshot能力

## Builder需要实现的部分

- 核验官方R-GAT路径及依赖版本并包装CLI
- 取得IGBH-large及校验和
- 建立重载质量与掩码泄漏检查；先做tiny再做容量画像

## 与相关任务的边界

本任务是异构节点主题分类；E10是带时间切分和负例的缺失引用排序。不同模型规模不另计任务。

## 数据血缘

- igbh

## 任务范围与条件

- IGBH-large是本派生参考规模，不能报告成MLPerf IGBH-Full成绩
- full特征历史更新需要在manifest中明确

## 来源记录

- [E_IGB] Illinois Graph Benchmark datasets — [来源](https://github.com/IllinoisGraphBenchmark/IGB-Datasets)；检查位置：Heterogeneous tiny/small/medium/large/full releases, real features, igb/train_multi_hetero.py, updated full features
- [E_RGAT_IMPL] MLPerf R-GAT reference implementation — [来源](https://github.com/mlcommons/training/tree/master/retired_benchmarks/rgat)；检查位置：README.md and train_rgnn_multi_gpu.py fetched from official raw source; model=rgat, dataset_size=large/full, 3 layers/512 hidden/4 heads/[15,10,5] sampling, CSC/FP16 and pin_feature
- [E_MLPERF_RGAT] MLPerf GNN benchmark introduction — [来源](https://mlcommons.org/2024/06/gnn-for-mlperf-training-v4/)；检查位置：IGBH-Full workload and Relational GAT benchmark with distributed GPU training

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
