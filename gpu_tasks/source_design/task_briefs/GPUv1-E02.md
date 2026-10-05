# GPUv1-E02 · 生成历史房贷逾期特征仓库

Build a historical mortgage delinquency feature mart

**组别**：GPU数据、向量与图计算　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`fannie_mortgage_delinquency_feature_mart`

**Workflow family**：`gpu_relational_analytics`

## 任务目标

把四年放款批次的原始记录构造成按贷款与月份组织的特征仓库，复现已声明的 delinquency_12 标签，交付可供后续建模直接读取的完整分区数据。

## 具体来源工作负载

NVIDIA MortgageETL.ipynb; Fannie Mae primary acquisition cohorts 2000Q1–2003Q4 and associated performance histories, frozen provider release

## 输入与配置

- 2000Q1–2003Q4 原生季度贷款文件及其对应月度历史；正式构建固定获取版本
- 官方 ETL 的 seller mapping、日期解析、标签和列规则
- 按贷款 ID 固定的训练/验证分组清单

## 需要完成的工作

- 解析原始字段并分离 acquisition/performance
- 构建贷款月度状态与 12 月标签，规范卖方和类别字段
- 物化按季度分区的完整特征仓库和可追踪拒绝记录

## 交付物

- feature_mart/ Parquet 分区
- schema.json、category_mapping.json
- loan_cohort_manifest.json 与构建程序

## 后续使用与状态

在保留的仓库上读取指定贷款批次，生成跨月逾期转移统计并核对标签。

## 独立验收

- 按贷款 ID 抽查原始历史到标签的完整演算
- 分区键、重复键、类别映射及空值符合规则
- 全量键覆盖与各季度行数校验；数值容差按独立 CPU 参考固定
- 标签只按声明时窗生成；后续查询真正读取已有产物

## 应拒绝的失败方式

- 用最新状态替代各月状态
- 月度 join 膨胀或重复贷款
- 训练/验证贷款泄漏
- 用仓库附带小样例冒充四年输入

## 规模配方

### Debug：仅调通

- **workload**：一个季度的固定贷款 ID 子集，保留这些贷款的完整历史
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：2000Q1–2003Q4 全部原生放款批次及其冻结性能历史；完整执行官方 ETL 逻辑
- **proposed_hardware_tier**：T3：2–4×80GiB GPU 的 Spark RAPIDS；主机 RAM、shuffle/NVMe 空间按资产清单规划
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：扩至 2000Q1–2007Q4 同一处理目标；多 worker shuffle 为独立部署场景
- **separate_task_id**：False

## GPU工作与预期资源形态

窗口标签、字符串映射、较大历史 join 和列式物化产生 GPU 数据处理及主机/磁盘交换；不是用训练轮数制造负载。

## 资源标签（待画像验证）

- gpu_dataflow
- join_shuffle
- host_device_transfer
- workspace_heavy
- multi_process

## 设备能力

- CUDA
- Spark RAPIDS SQLPlugin

## 后端要求

- 固定 Spark/Java/RAPIDS/CUDA 兼容组合
- executor 的 GPU 和 CPU、内存预算显式登记
- 源数据预先按许可取得并作为只读输入

## 回放约束

- 冻结月度数据截止日期及日历语义
- Spark session 跨后续查询存活；job ID 动态绑定
- 真实 shuffle/写回与后台 executor 生命周期继续测量

## Builder需要实现的部分

- 合法获取源文件、生成 immutable manifest
- 包装官方 ETL 并新增任务产物协议
- 独立实现标签抽查与全量键核对

## 与相关任务的边界

目标是有时间语义的特征仓库，E03/E04 交付训练后模型；若 CPU 包已有同一仓库目标，只增加 GPU 执行变体。

## 数据血缘

- fannie_mae_single_family_2000_2003

## 任务范围与条件

- 数据访问及再分发受提供方条款约束，ZIP 不含贷款数据
- 应用派生协议不复制 upstream 云集群性能结论

## 来源记录

- [E_MORTGAGE_ETL] MortgageETL notebook — [来源](https://github.com/NVIDIA/cudf-spark-examples/blob/main/examples/XGBoost-Examples/mortgage/notebooks/python/MortgageETL.ipynb)；检查位置：Notebook code cells: raw loan schema, acquisition/performance extraction, delinquency_12, Spark SQLPlugin; raw source also inspected
- [E_FANNIE] Single-Family Loan Performance Data — [来源](https://capitalmarkets.fanniemae.com/credit-risk-transfer/fannie-mae-single-family-loan-performance-data)；检查位置：Primary acquisition/performance dataset, access link and release information
- [E_SPARK_EXAMPLES] Spark XGBoost examples — [来源](https://github.com/NVIDIA/cudf-spark-examples/tree/main/examples/XGBoost-Examples)；检查位置：Mortgage and Taxi blueprints; larger upstream datasets required for performance use

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
