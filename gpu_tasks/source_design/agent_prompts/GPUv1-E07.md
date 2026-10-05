# GPUv1-E07 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

为给定历史关注图生成结构优先级排行和完整节点分值表，提供稳定 ID 映射与指定节点的局部报告，供离线图数据分析使用。

### 来源和工作范围

LAW twitter-2010 full graph; reverse published message-flow arcs to follower→followed; cuGraph PageRank

### 交付要求

- node_scores.parquet
- top_nodes.parquet
- vertex_mapping_manifest.json
- 可复用图 worker 与查询程序

### 必须完成的工作

- 将原图解码成固定分片并核对方向、ID、重复边
- 加载 GPU 图并计算收敛的全图 PageRank
- 导出完整分值、排序摘要与指定节点统计

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

在保留图上响应另一组固定节点 ID 的分值与度数查询，无需重新下载或解码图。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
