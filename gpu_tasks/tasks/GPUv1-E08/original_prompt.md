# GPUv1-E08 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

把完整友情图整理成社区清单，给出每个节点的社区、社区大小及跨社区边汇总，并提供可查询的社区目录。

### 来源和工作范围

SNAP com-Friendster full undirected graph and top5000 community annotations; cuGraph distributed Louvain

### 交付要求

- vertex_community.parquet
- communities.parquet
- community_links.parquet
- community_manifest.json

### 必须完成的工作

- 规范无向边并建立分布式 GPU 图
- 执行社区优化并生成节点分区
- 汇总社区规模与跨社区边，发布查询目录

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

从已发布目录抽取指定社区的成员与跨社区连接摘要，核对其与全量划分一致。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
