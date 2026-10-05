# GPUv1-E04 · 构建年度出租车费用回归与审计模型

Build an annual taxi fare regression and audit model

**组别**：GPU数据、向量与图计算　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`nyc_taxi_fare_audit_regressor`

**Workflow family**：`gpu_boosted_tree_learning`

## 任务目标

利用全年出租车行程建立费用回归模型，对未参与训练的月份给出逐行预测、残差及按区域/时段的误差表，用于历史费用审计。

## 具体来源工作负载

NVIDIA taxi-gpu.ipynb SparkXGBRegressor; NYC TLC Yellow Taxi 2019 monthly Parquet records

## 输入与配置

- 2019 年 12 个月 Yellow Taxi 原生 Parquet
- 2019-01 至 2019-09 训练，10 月验证，11–12 月测试
- 目标 fare_amount；pickup/dropoff zone、行程距离、人数、费率类别和时间特征；明确排除总价、税额、小费等目标派生字段

## 需要完成的工作

- 规范每月字段和过滤无效记录并保留拒绝清单
- 在 GPU ETL 后训练 CUDA SparkXGBRegressor
- 持久化并重新加载模型，对完整测试月份预测和汇总残差

## 交付物

- taxi_model/
- test_predictions.parquet
- fare_error_by_zone_time.parquet
- feature_pipeline.py 与数据清单

## 后续使用与状态

使用保留模型对另一个已冻结月份切片运行审计，生成可追溯异常候选清单而不重新训练。

## 独立验收

- 重载模型对固定隐藏测试行复算；RMSE/MAE 与参考容差比较
- 月份互斥且测试覆盖所有通过同一清洗规则的行
- 预测和残差表按行 ID 对齐
- 禁止目标派生字段；GPU 路径与数据覆盖独立验收

## 应拒绝的失败方式

- 随机混合月份导致测试泄漏
- 用 total_amount 直接推 fare_amount
- 把交易后模型误称为上车前报价器
- 仅运行仓库演示 CSV

## 规模配方

### Debug：仅调通

- **workload**：2019-01 的固定若干日及独立日验证，仅调试
- **formal_admission**：False

### Reference large：正式生产规模

- **workload**：2019 全部 Yellow Taxi 月度文件；时间切分后完整训练/测试；官方 GPU 回归流程按现代 TLC schema 映射
- **proposed_hardware_tier**：T2：单 80GiB GPU 或固定 2×48GiB Spark GPU worker；主机/NVMe 容量依实际源文件规划
- **measured_requirement**：False

### 可选扩展：同一任务的变体

- **workload**：保持 2019 测试集，加入 2017–2018 原生训练月份形成同任务规模扩展；重采集对应轨迹
- **separate_task_id**：False

## GPU工作与预期资源形态

全年真实行程的列处理、量化和回归训练兼具 GPU 计算、数据搬运与输入扫描，能覆盖数据准备到模型复用的阶段切换。

## 资源标签（待画像验证）

- gpu_dataflow
- gpu_tree_training
- stage_changes
- persistent_model
- storage_read_write

## 设备能力

- CUDA
- Spark RAPIDS
- SparkXGBRegressor

## 后端要求

- Spark/CUDA 与 XGBoost GPU 依赖固定
- 明确 executor 和 pinned-host-memory 预算

## 回放约束

- 保留清洗规则、时间切分、字段 schema 和训练停止条件
- 按真实训练/推理完成事件衔接
- Spark worker/端口映射为运行时绑定

## Builder需要实现的部分

- 下载2019月度数据并冻结schema
- 将官方经纬度示例适配为2019区域字段，不复制样例结果
- 实现逐行预测与误差验证器

## 与相关任务的边界

E03 为二分类事件模型；本任务有时间外推、回归目标和完整费用审计产物。若已有 CPU 同数据同目标任务，登记为 GPU variant。

## 数据血缘

- nyc_tlc_yellow_2019

## 任务范围与条件

- 官方样例和现代 TLC 字段不同，适配是显式新增 builder 工作
- 异常候选只用于数据质量审计，不推断个体违法行为

## 来源记录

- [E_TAXI_GPU] Taxi GPU regression notebook — [来源](https://github.com/NVIDIA/cudf-spark-examples/blob/main/examples/XGBoost-Examples/taxi/notebooks/python/taxi-gpu.ipynb)；检查位置：Raw notebook inspected: fare_amount target, SparkXGBRegressor device=cuda, save/load and RMSE evaluation
- [E_TLC] NYC TLC Trip Record Data — [来源](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)；检查位置：Monthly Yellow Taxi Parquet download lists including 2015 and 2019, schema/errata information
- [E_SPARK_EXAMPLES] Spark XGBoost examples — [来源](https://github.com/NVIDIA/cudf-spark-examples/tree/main/examples/XGBoost-Examples)；检查位置：Mortgage and Taxi blueprints; larger upstream datasets required for performance use
- [E_XGB] XGBoost GPU support — [来源](https://xgboost.readthedocs.io/en/stable/gpu/index.html)；检查位置：device=cuda, tree_method=hist, QuantileDMatrix, GPU prediction and distributed execution

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
