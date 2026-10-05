# GPUv1-E06 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

把大型视觉向量库按内容相近程度分成可用于后续分发和分析的分区，交付每个向量的分区 ID、中心和分区统计，并支持新向量归类。

### 来源和工作范围

DEEP1B first 100M 96-D vectors; cuVS K-Means fit/predict with persistent centroids and full assignment output

### 交付要求

- centroids.npy
- assignments/ Parquet 分片
- cluster_inventory.parquet
- fit_manifest.json 与归类 CLI

### 必须完成的工作

- 在 GPU 进行真实 K-Means 拟合与全量最近中心分配
- 输出完整 ID→cluster 映射、中心与计数/距离摘要
- 重载中心为未参与拟合的新向量分配分区

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

对真实 query 文件逐条归类，更新分区计数并保持已发布分区 ID 的定义。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
