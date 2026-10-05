# GPUv1-E02 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

把四年放款批次的原始记录构造成按贷款与月份组织的特征仓库，复现已声明的 delinquency_12 标签，交付可供后续建模直接读取的完整分区数据。

### 来源和工作范围

NVIDIA MortgageETL.ipynb; Fannie Mae primary acquisition cohorts 2000Q1–2003Q4 and associated performance histories, frozen provider release

### 交付要求

- feature_mart/ Parquet 分区
- schema.json、category_mapping.json
- loan_cohort_manifest.json 与构建程序

### 必须完成的工作

- 解析原始字段并分离 acquisition/performance
- 构建贷款月度状态与 12 月标签，规范卖方和类别字段
- 物化按季度分区的完整特征仓库和可追踪拒绝记录

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

在保留的仓库上读取指定贷款批次，生成跨月逾期转移统计并核对标签。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
