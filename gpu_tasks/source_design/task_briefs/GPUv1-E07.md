# GPUv1-E07 · 生成大型历史关注图的节点优先级报告

Rank a large historical follow graph

**组别**：GPU数据、向量与图计算　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`twitter2010_follow_graph_ranking`

**Workflow family**：`gpu_graph_analytics`

## 任务目标

为给定历史关注图生成结构优先级排行和完整节点分值表，提供稳定 ID 映射与指定节点的局部报告，供离线图数据分析使用。

## 具体来源工作负载

LAW twitter-2010 full graph; reverse published message-flow arcs to follower→followed; cuGraph PageRank

## 输入与配置

- twitter-2010 完整41,652,230节点、1,468,365,182弧
- 原始ID映射；方向清单声明对源消息流边取转置
- PageRank alpha与收敛规则在参考配置冻结

## 需要完成的工作

- 将原图解码成固定分片并核对方向、ID、重复边
- 加载 GPU 图并计算收敛的全图 PageRank
- 导出完整分值、排序摘要与指定节点统计

## 交付物

- node_scores.parquet
- top_nodes.parquet
- vertex_mapping_manifest.json
- 可复用图 worker 与查询程序

## 后续使用与状态

在保留图上响应另一组固定节点 ID 的分值与度数查询，无需重新下载或解码图。

## 独立验收

- 节点覆盖、边数与转置方向正确
- 概率非负、归一化和迭代残差按参考数值容差检验
- 独立参考排行在允许并列/浮点误差下匹配
- 随机隐藏节点实际读取保留图/分值

## 应拒绝的失败方式

- 错误解释源边方向
- 将度数排行伪装为PageRank
- 仅处理最大分片
- 将未收敛结果标记成功

## 规模配方

### Debug：仅调通

- **workload**：固定种子节点构成的诱导子图，仅调试
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：twitter-2010全量图；完成收敛计算及完整节点结果导出
- **proposed_hardware_tier**：T3：2–4×80GiB GPU，足够主机 RAM 与 NVMe 解码空间；可行性待画像
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：同一全图在2/4/8GPU间分片；源数据不复制成更大假图
- **separate_task_id**：False

## GPU工作与预期资源形态

十亿级边遍历与稀疏归约需要真实图状态、显存带宽和跨卡消息交换；和 dense训练的执行路径不同。

## 资源标签（待画像验证）

- gpu_sparse_graph
- gpu_memory_bandwidth
- gpu_collectives
- graph_residency
- large_input

## 设备能力

- CUDA
- cuGraph
- Dask-cuDF for multi-GPU

## 后端要求

- 64位边数量与适当顶点ID类型
- 声明UCX、跨卡连接与每GPU worker映射；无RDMA默认要求

## 回放约束

- 固定转置、重编号和图分片规则
- 图worker跨等待保留，后续查询读取真实状态
- Dask job ID/端口运行时绑定

## Builder需要实现的部分

- 解码源图并固定分片和ID映射
- 建立收敛/残差及全量覆盖验证
- 包装persistent图查询接口

## 与相关任务的边界

结构排行任务，与 E08 的无向社区划分和 E09/E10 的监督学习目标不同。

## 数据血缘

- law_twitter2010

## 任务范围与条件

- 结构分值不宣称为现实中的个人影响力
- 源图压缩文件体积不能代替展开图的显存需求

## 来源记录

- [E_TWITTER] twitter-2010 graph — [来源](https://law.di.unimi.it/webdata/twitter-2010/)；检查位置：41,652,230 vertices, 1,468,365,182 arcs, raw arc direction and original-ID mapping
- [E_PAGERANK] Distributed cuGraph PageRank — [来源](https://docs.nvidia.com/cugraph/latest/api_docs/api/cugraph/cugraph.dask.link_analysis.pagerank.pagerank/)；检查位置：Multi-GPU API, dask-cuDF edge partitions, convergence flag and personalization

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
