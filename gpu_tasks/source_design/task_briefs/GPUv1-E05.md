# GPUv1-E05 · 构建亿级图像描述子检索索引

Build a hundred-million-image-descriptor retrieval index

**组别**：GPU数据、向量与图计算　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`bigann_sift_retrieval_index`

**Workflow family**：`gpu_ann_indexing`

## 任务目标

为给定图像描述子库建立可持久化的相似检索索引，返回查询的近邻 ID 和距离，并让后续查询可以使用同一个已加载索引。

## 具体来源工作负载

BIGANN/SIFT1B first 100M base descriptors and matching public queries/100M ground truth; Faiss GpuIndexIVFPQ

## 输入与配置

- BIGANN 原生前 100M 个 128 维描述子
- 与 100M 前缀严格匹配的官方查询/ground truth
- 统一 L2 距离、原始向量 ID；IVF-PQ 训练样本和码本种子固定

## 需要完成的工作

- 以分批输入训练 GPU 量化器、建立并填充实际索引
- 在 GPU 执行查询并记录真实近邻结果
- 按官方 GPU→CPU 序列化路径持久化，再载入 GPU 验证

## 交付物

- index.faiss 与 index_manifest.json
- query_neighbors.parquet
- 可被后续调用使用的索引 worker 与查询 CLI

## 后续使用与状态

对第一阶段未使用的真实 query 子集查询；保留索引，比较保存/重载前后的内容语义。

## 独立验收

- ntotal、向量 ID 范围和来源哈希正确
- 用匹配 100M 的 ground truth 计算 recall，阈值由冻结参考配置校准
- 隐藏查询重新执行，不能复制公开结果
- 索引重载后查询质量和距离在参考容差内

## 应拒绝的失败方式

- 加载 10M 前缀却使用 100M 名称
- 查询时直接返回 ground truth
- 仅 CPU IVF 查询
- 持久化空壳或索引与 ID 映射不一致

## 规模配方

### Debug：仅调通

- **workload**：官方 1M/10M 对应子集和 ground truth；仅调试
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：BIGANN 原生 100M 前缀全量入索引并执行官方 10K 查询；IVF-PQ 的 nlist/code size/nprobe 在参考采集前冻结
- **proposed_hardware_tier**：T2：单80GiB GPU；压缩索引可能在 T1 可行，必须实测决定
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：完整 BIGANN 1B 为 advanced：2–8 GPU IndexShards，分批 add、主机映射和 NVMe 空间明确；不是新任务
- **separate_task_id**：False

## GPU工作与预期资源形态

索引构建、距离计算、长期索引驻留、查询临时缓冲与序列化搬运提供不同于训练的 GPU 资源形态。

## 资源标签（待画像验证）

- gpu_ann_build
- gpu_memory_resident
- burst_queries
- host_device_transfer
- large_workspace

## 设备能力

- CUDA
- Faiss GPU IVF-PQ

## 后端要求

- 必须安装带 GPU 的 Faiss；显式登记 scratch 与 ID 存储位置
- 跨卡分片才启用对应可见设备；不假设多卡复制节省容量

## 回放约束

- 索引句柄与服务地址动态绑定
- CUDA streams 与查询完成正确同步
- 应用索引文件恢复不等于 GPU context 或 VM snapshot

## Builder需要实现的部分

- 下载匹配前缀/ground truth并哈希
- 包装 persistent worker、索引导出与重载
- 校准 recall 与资源画像，保证训练样本不来自公开答案

## 与相关任务的边界

交付可查询索引；E06 交付集合分区而非相似检索。与此前 Memory 包若使用同一 ANN 任务应共享 canonical ID 并标记 GPU variant。

## 数据血缘

- bigann_sift1b

## 任务范围与条件

- 压缩程度会显著改变显存，不能仅用原始向量字节称为显存需求
- CPU 序列化阶段属于实际任务成本

## 来源记录

- [E_BIGANN] NeurIPS 2021 Billion-Scale ANN challenge datasets — [来源](https://big-ann-benchmarks.com/neurips21.html)；检查位置：Dataset collection and billion-scale nearest-neighbor benchmark links
- [E_FAISS_1G] Indexing 1G vectors — [来源](https://github.com/facebookresearch/faiss/wiki/Indexing-1G-vectors)；检查位置：BIGANN 128-D SIFT and Deep1B 96-D descriptors; 10M/100M/1B scale usage
- [E_FAISS_GPU] Faiss on the GPU — [来源](https://github.com/facebookresearch/faiss/wiki/Faiss-on-the-GPU)；检查位置：GpuIndexIVFPQ, batched add/search, scratch state, sharding, CPU conversion before index serialization
- [E_CUVS_DATA] cuVS benchmark datasets — [来源](https://docs.nvidia.com/cuvs/user-guide/benchmarking-guide/cu-vs-bench-tool/datasets)；检查位置：base/query/groundtruth file formats and matching 10M/100M subsets of billion-scale sources

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
