# GPUv1-E04 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

利用全年出租车行程建立费用回归模型，对未参与训练的月份给出逐行预测、残差及按区域/时段的误差表，用于历史费用审计。

### 来源和工作范围

NVIDIA taxi-gpu.ipynb SparkXGBRegressor; NYC TLC Yellow Taxi 2019 monthly Parquet records

### 交付要求

- taxi_model/
- test_predictions.parquet
- fare_error_by_zone_time.parquet
- feature_pipeline.py 与数据清单

### 必须完成的工作

- 规范每月字段和过滤无效记录并保留拒绝清单
- 在 GPU ETL 后训练 CUDA SparkXGBRegressor
- 持久化并重新加载模型，对完整测试月份预测和汇总残差

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

使用保留模型对另一个已冻结月份切片运行审计，生成可追溯异常候选清单而不重新训练。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
