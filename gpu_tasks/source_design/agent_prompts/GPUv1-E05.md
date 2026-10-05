# GPUv1-E05 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

为给定图像描述子库建立可持久化的相似检索索引，返回查询的近邻 ID 和距离，并让后续查询可以使用同一个已加载索引。

### 来源和工作范围

BIGANN/SIFT1B first 100M base descriptors and matching public queries/100M ground truth; Faiss GpuIndexIVFPQ

### 交付要求

- index.faiss 与 index_manifest.json
- query_neighbors.parquet
- 可被后续调用使用的索引 worker 与查询 CLI

### 必须完成的工作

- 以分批输入训练 GPU 量化器、建立并填充实际索引
- 在 GPU 执行查询并记录真实近邻结果
- 按官方 GPU→CPU 序列化路径持久化，再载入 GPU 验证

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

对第一阶段未使用的真实 query 子集查询；保留索引，比较保存/重载前后的内容语义。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
