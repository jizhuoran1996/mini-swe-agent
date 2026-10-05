# GPUv1-E06 · 为大型视觉向量库生成内容分区

Partition a large visual-vector collection by content

**组别**：GPU数据、向量与图计算　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`deep1b_collection_partition`

**Workflow family**：`gpu_vector_clustering`

## 任务目标

把大型视觉向量库按内容相近程度分成可用于后续分发和分析的分区，交付每个向量的分区 ID、中心和分区统计，并支持新向量归类。

## 具体来源工作负载

DEEP1B first 100M 96-D vectors; cuVS K-Means fit/predict with persistent centroids and full assignment output

## 输入与配置

- DEEP1B 原生 100M 前缀、96维浮点向量
- K=4096 的分区目标和 L2 距离；初始化 seed 与默认收敛设置固定
- 独立 query 向量用作后续归类输入

## 需要完成的工作

- 在 GPU 进行真实 K-Means 拟合与全量最近中心分配
- 输出完整 ID→cluster 映射、中心与计数/距离摘要
- 重载中心为未参与拟合的新向量分配分区

## 交付物

- centroids.npy
- assignments/ Parquet 分片
- cluster_inventory.parquet
- fit_manifest.json 与归类 CLI

## 后续使用与状态

对真实 query 文件逐条归类，更新分区计数并保持已发布分区 ID 的定义。

## 独立验收

- 所有输入 ID 恰好出现一次；分区数、形状和总计数匹配
- 抽查分配是否为中心的最近邻，误差按参考精度校准
- 独立重算抽样 inertia，并与冻结参考范围比较
- 中心和分区标签可置换等价，不要求逐字节相同

## 应拒绝的失败方式

- 所有向量被分到同一分区
- 只输出抽样分配
- 利用重复向量增加规模
- 每次续接重新拟合却声称保留原中心

## 规模配方

### Debug：仅调通

- **workload**：DEEP 原生 1M 前缀用于接口调试；正式分区目标不由复制扩容
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：DEEP1B 前 100M 向量完整拟合/分配；K=4096、一次初始化、按参考收敛规则停止
- **proposed_hardware_tier**：T2：单80GiB GPU，或明确 host-streaming cuVS 路径；不要求所有数据一次复制入显存
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：完整1B为advanced，可用host streaming；2–8GPU路径需为cuVS官方多GPU C++ RAFT/NCCL API编写薄CLI适配并独立验证，Python单卡入口不会自动多卡；固定读批次和收敛条件
- **separate_task_id**：False

## GPU工作与预期资源形态

迭代距离计算、归约与大集合赋值提供持续有效计算；host streaming 与驻留执行可区分传输和显存策略。

## 资源标签（待画像验证）

- gpu_dense_distance
- gpu_reductions
- gpu_memory_resident
- host_streaming_optional
- large_outputs

## 设备能力

- CUDA
- cuVS K-Means fit/predict
- 可选多GPU：C++ RAFT/NCCL调用与经过验证的薄CLI适配

## 后端要求

- 固定 cuVS/CUDA 与数据类型
- 流式拟合必须在版本中实际支持，不能默默替换成 sklearn CPU
- 可选多GPU构建需匹配C++ ABI/RAFT/NCCL并声明通信拓扑；不从单卡Python入口隐式扩展

## 回放约束

- 固定原始向量和收敛规则；不同规模重新收集轨迹
- centroid worker 的 GPU 内存和等待阶段均保留计量
- 异步 fit/predict 确认完成后发布结果

## Builder需要实现的部分

- 构造100M输入manifest
- 实现完整赋值与分区统计导出
- 建立置换不变校验和参考质量区间
- 若启用多GPU：实现C++ RAFT/NCCL API薄CLI，校验分片计数、中心归约、完整分配和重载一致性

## 与相关任务的边界

这是集合内容组织，不是换一种 ANN 算法再计一个任务；与 E05 的查询索引有不同最终数据产品。

## 数据血缘

- deep1b

## 任务范围与条件

- K=4096是本派生任务的分区配置，不是上游官方排名参数
- 不能用强制重复迭代替代真实收敛

## 来源记录

- [E_FAISS_1G] Indexing 1G vectors — [来源](https://github.com/facebookresearch/faiss/wiki/Indexing-1G-vectors)；检查位置：BIGANN 128-D SIFT and Deep1B 96-D descriptors; 10M/100M/1B scale usage
- [E_CUVS_DATA] cuVS benchmark datasets — [来源](https://docs.nvidia.com/cuvs/user-guide/benchmarking-guide/cu-vs-bench-tool/datasets)；检查位置：base/query/groundtruth file formats and matching 10M/100M subsets of billion-scale sources
- [E_CUVS_KMEANS] cuVS K-Means guide — [来源](https://docs.nvidia.com/cuvs/user-guide/api-guides/clustering-guide/k-means)；检查位置：fit/predict, centroids and assignments, convergence, host streaming, balanced and multi-GPU links

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
