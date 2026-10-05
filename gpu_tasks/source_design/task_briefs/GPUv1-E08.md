# GPUv1-E08 · 建立全量 Friendster 社区与跨社区连接清单

Build a Friendster community and inter-community inventory

**组别**：GPU数据、向量与图计算　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`friendster_community_inventory`

**Workflow family**：`gpu_graph_analytics`

## 任务目标

把完整友情图整理成社区清单，给出每个节点的社区、社区大小及跨社区边汇总，并提供可查询的社区目录。

## 具体来源工作负载

SNAP com-Friendster full undirected graph and top5000 community annotations; cuGraph distributed Louvain

## 输入与配置

- com-friendster.ungraph.txt.gz 全量65,608,366节点/1,806,067,135无向边
- com-friendster.top5000.cmty.txt.gz 用作分析参考
- 固定resolution、停止规则及无向边去重语义

## 需要完成的工作

- 规范无向边并建立分布式 GPU 图
- 执行社区优化并生成节点分区
- 汇总社区规模与跨社区边，发布查询目录

## 交付物

- vertex_community.parquet
- communities.parquet
- community_links.parquet
- community_manifest.json

## 后续使用与状态

从已发布目录抽取指定社区的成员与跨社区连接摘要，核对其与全量划分一致。

## 独立验收

- 全部顶点有且仅有一个输出分区，边计数与去重规则一致
- 独立重算模块度/edge cut及社区汇总，质量区间由参考校准
- 标签置换视为等价，不逐字节比较社区编号
- 源用户群有重叠，仅用于辅助对照，不能要求Louvain非重叠划分逐一相等

## 应拒绝的失败方式

- 一个巨型社区或全单点的退化输出蒙混过关
- 截断边文件
- 把源top5000群组直接当计算结果
- 重复双向边造成统计翻倍

## 规模配方

### Debug：仅调通

- **workload**：固定诱导子图与同一划分/汇总流程，仅调试
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：完整Friendster图，实际计算分区和跨社区清单
- **proposed_hardware_tier**：T3：4–8×80GiB GPU，主机RAM/临时空间按展开图和双向存储规划
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：在同一完整图上变化GPU数/分片；不额外制造重复边
- **separate_task_id**：False

## GPU工作与预期资源形态

大图构造、社区迭代、重编号和全图汇总产生显存容量、带宽、跨卡通信与可写产物压力。

## 资源标签（待画像验证）

- gpu_sparse_graph
- irregular_access
- gpu_collectives
- large_workspace
- graph_residency

## 设备能力

- CUDA
- distributed cuGraph Louvain

## 后端要求

- 多GPU可见并允许所需IPC/UCX
- 后端预算包括图解码、Dask worker与中间图状态

## 回放约束

- 固定图hash、算法版本和分区参数
- 算法标签非确定性由置换不变验证处理
- 全量CUDA和汇总输出完成后才发布目录

## Builder需要实现的部分

- 构建源图转换器和完整性检查
- 实现模块度/跨社区统计独立校验
- 容量预检后收集正式轨迹

## 与相关任务的边界

与 E07 在不同原生图上交付社区及关系目录；不是将同一图更换算法后重复计数。

## 数据血缘

- snap_friendster

## 任务范围与条件

- Louvain结果存在数值和调度非确定性
- 完整图可能要求较多主机/设备内存；未实测前不承诺单卡可运行

## 来源记录

- [E_FRIENDSTER] Friendster social network and communities — [来源](https://snap.stanford.edu/data/com-Friendster.html)；检查位置：com-friendster.ungraph.txt.gz, ground-truth communities; 65,608,366 nodes and 1,806,067,135 edges
- [E_LOUVAIN] Distributed cuGraph Louvain — [来源](https://docs.nvidia.com/cugraph/latest/api_docs/api/cugraph/cugraph.dask.community.louvain.louvain/)；检查位置：Undirected input requirement, resolution, modularity gain termination, partitions and modularity outputs

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
