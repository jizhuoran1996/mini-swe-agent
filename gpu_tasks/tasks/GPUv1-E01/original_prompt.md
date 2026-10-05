# GPUv1-E01 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

把给定订单数据库整理成可复查的国家—年份收入表、产品利润表和运输方式履约表，交付可重新运行的 GPU 分析程序和 Parquet 结果。

### 来源和工作范围

cuDF-Polars PDS-H; tpchgen-cli SF1000; lineitem/orders/customer/supplier/part/partsupp/nation/region tables; source query families Q5/Q9/Q12

### 交付要求

- revenue_by_nation_year.parquet
- product_profit.parquet
- shipping_summary.parquet
- pipeline.py 与输入/计划/输出清单

### 必须完成的工作

- 核对键和日期类型，完成事实表与维表连接
- 用 GPU 执行所需过滤、连接和聚合并物化结果
- 保存查询计划及结果血缘，处理超出显存的数据分区

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

在已有数据和执行环境上增加一个已声明年份的下钻报告，验证与总表可对账。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
