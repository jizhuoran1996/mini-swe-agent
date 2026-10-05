# GPUv1-E10 · 训练缺失引用推荐模型

Train a missing-citation recommender

**组别**：GPU数据、向量与图计算　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`ogbl_citation2_missing_reference_recommender`

**Workflow family**：`gpu_gnn_learning`

## 任务目标

根据已有论文特征和引用关系训练缺失参考文献推荐器，提交可重载模型和每个保留查询的候选排序，支持后续论文查询。

## 具体来源工作负载

OGBL-Citation2 full 2,927,963 nodes / 30,561,187 edges; official sampler.py GraphSAGE [15,10,5], three layers, 256 hidden channels

## 输入与配置

- ogbl-citation2 全量图、128维特征与时间切分
- 官方验证/测试正例及各1000负例候选
- 官方sampler.py GraphSAGE配置；一次训练run，固定采样器seed

## 需要完成的工作

- 建立只含训练边的采样图
- 在GPU执行邻居采样批次的GraphSAGE和link predictor训练
- 用官方Evaluator计算MRR并保存逐query排序和checkpoint

## 交付物

- citation_model.pt 与 predictor_state.pt
- query_rankings.parquet
- split_and_sampling_manifest.json
- recommend.py

## 后续使用与状态

用保留模型处理另一组固定论文和候选引用，确保不将新查询答案加入训练图。

## 独立验收

- 图中不含验证/测试被隐藏边；官方负例文件版本正确
- 独立重载计算MRR，阈值/数值容差从固定参考校准
- 逐查询候选集合、顺序和行ID齐全
- 禁止使用旧ogbl-citation的有偏负例

## 应拒绝的失败方式

- 标签边泄漏
- 复制公开排行榜成绩但无模型
- 改变负例集合提升MRR
- 只输出少量好预测查询

## 规模配方

### Debug：仅调通

- **workload**：保留依赖的一小段官方训练节点采样，仅调试
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：全量ogbl-citation2，官方GraphSAGE sampler配置；单run默认150epoch上限，参考采集前冻结停止与验证周期；保留完整测试
- **proposed_hardware_tier**：T2：单80GiB GPU或T1采样路径，主机RAM用于图/特征；绝不把所有邻域一次放入显存
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：相同任务可使用官方full-batch GNN作为执行变体，需先确认容量；多卡移植需要额外builder，不能自动宣称支持
- **separate_task_id**：False

## GPU工作与预期资源形态

持续有监督采样、图特征传输、稀疏聚合、梯度更新和大候选集推理，覆盖GNN训练及后续模型驻留。

## 资源标签（待画像验证）

- gpu_gnn_training
- neighbor_sampling
- host_device_transfer
- large_candidate_inference
- persistent_model

## 设备能力

- CUDA
- PyTorch Geometric
- OGB Evaluator

## 后端要求

- 固定PyG采样依赖与CUDA版本
- CPU采样与GPU训练阶段分别计量
- 保留图文件、模型和采样worker的完整生命周期

## 回放约束

- 只固定LLM侧输出；采样/训练/推理执行真实工作
- 固定随机seed和源版本，不要求不同GPU逐字节一致
- 动态job/模型句柄由运行绑定恢复

## Builder需要实现的部分

- 包装官方sampler加入checkpoint/重载/输出协议
- 固定单run训练配方并校准质量
- 实现泄漏检查与逐query隐藏复算

## 与相关任务的边界

E09为节点分类；本任务学习有时间约束的边排序，与D组文本embedding/reranking服务无重复。

## 数据血缘

- ogbl_citation2

## 任务范围与条件

- 上游默认10 runs是论文统计重复；这里单次任务只训练一次，不用重复run凑负载
- 正式epoch预算/停止规则需参考运行冻结，当前没有测得时长

## 来源记录

- [E_OGB_CITATION] OGBL-Citation2 task — [来源](https://ogb.stanford.edu/docs/linkprop/)；检查位置：ogbl-citation2 node/edge counts, chronological split, missing citation task, 1000 negatives and MRR
- [E_OGB_GPU] OGBL-Citation2 official GNN examples — [来源](https://github.com/snap-stanford/ogb/tree/master/examples/linkproppred/citation2)；检查位置：README.md, gnn.py and sampler.py fetched from official raw source; CUDA, GraphSAGE, [15,10,5] sampling, source defaults

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
