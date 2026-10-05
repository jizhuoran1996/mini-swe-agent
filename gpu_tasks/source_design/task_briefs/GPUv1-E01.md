# GPUv1-E01 · 构建大规模订单收入与履约分析数据集

Materialize an order revenue and fulfillment report

**组别**：GPU数据、向量与图计算　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`pdsh_revenue_fulfillment_mart`

**Workflow family**：`gpu_relational_analytics`

## 任务目标

把给定订单数据库整理成可复查的国家—年份收入表、产品利润表和运输方式履约表，交付可重新运行的 GPU 分析程序和 Parquet 结果。

## 具体来源工作负载

cuDF-Polars PDS-H; tpchgen-cli SF1000; lineitem/orders/customer/supplier/part/partsupp/nation/region tables; source query families Q5/Q9/Q12

## 输入与配置

- tpchgen-cli 固定版本生成的 PDS-H SF1000 全套八张表
- Q5/Q9/Q12 各自的国家/产品/运输方式、日期范围与字符串参数逐项固定；保留原查询连接和聚合语义
- 源表校验和与统一 decimal/float 规则

## 需要完成的工作

- 核对键和日期类型，完成事实表与维表连接
- 用 GPU 执行所需过滤、连接和聚合并物化结果
- 保存查询计划及结果血缘，处理超出显存的数据分区

## 交付物

- revenue_by_nation_year.parquet
- product_profit.parquet
- shipping_summary.parquet
- pipeline.py 与输入/计划/输出清单

## 后续使用与状态

在已有数据和执行环境上增加一个已声明年份的下钻报告，验证与总表可对账。

## 独立验收

- 三份表的主键、行数和排序后结果与独立参考一致；金额精度按参考校准
- 输入全表覆盖与聚合守恒检查
- 重新加载产物完成下钻，不接受只有 benchmark timing JSON
- GPU 准入另查主要连接/聚合执行路径，CPU-only fallback 不计为 GPU 实例

## 应拒绝的失败方式

- 只跑 LIMIT 或小样本
- 改变连接类型造成丢行
- 金额列精度变化未记录
- 生成结果日志但未写实际表

## 规模配方

### Debug：仅调通

- **workload**：SF1 全表及相同报表，仅作调试
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：SF1000 全套原生生成表，一次完成三个互相关联报表；使用 GPU streaming engine
- **proposed_hardware_tier**：T2：单 80GiB GPU，工程目标配足主机内存、NVMe 输入/临时空间；不要求全表驻留显存
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：同一 SF1000 用 2–8 GPU Ray/UCX；SF3000 为同任务可选规模，固定通信与缓存配置
- **separate_task_id**：False

## GPU工作与预期资源形态

大事实表扫描、哈希连接、聚合、分区交换和 host↔device 搬运均执行真实数据工作，覆盖显存容量之外的流式执行。

## 资源标签（待画像验证）

- gpu_dataflow
- host_device_transfer
- gpu_memory_spill
- storage_read_write
- multi_gpu_optional

## 设备能力

- CUDA
- cuDF-Polars streaming

## 后端要求

- GPU 设备可见；固定 cuDF/Polars/CUDA 组合
- Ray 多卡路径需足够 /dev/shm 与 UCX；默认不假设 RDMA

## 回放约束

- 锁定生成器 seed/版本、分区和查询语义
- 异步任务以完成事件结束，记录真实 spill/写回
- 环境端口与 Ray job ID 为运行绑定

## Builder需要实现的部分

- 生成正式表与参考结果
- 适配三报表 CLI、原子发布与校验器
- 检查 GPU explain/trace；冻结 CPU fallback 策略

## 与相关任务的边界

与向量索引、树模型任务的交付语义不同；若已有 I/O/Memory 包使用相同 PDS-H 报表，应作为同 canonical task 的 GPU 执行变体。

## 数据血缘

- tpc_h_pdsh

## 任务范围与条件

- PDS-H 派生应用，不宣称 TPC-H 合规成绩
- SF1000 是数据规模配置，不是显存需求或实测时间

## 来源记录

- [E_PDSH] cuDF-Polars PDS-H benchmark — [来源](https://docs.nvidia.com/cudf/26.10/cudf_polars/benchmarks/)；检查位置：PDS-H setup, tpchgen-cli SF1000 generation, spmd/ray frontends, spill and pinned-memory controls
- [E_POLARS] Polars GPU engine — [来源](https://docs.nvidia.com/cudf/latest/cudf_polars/)；检查位置：GPU query plans, fallback behavior, PDS-H/PDS-DS large scale examples

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
