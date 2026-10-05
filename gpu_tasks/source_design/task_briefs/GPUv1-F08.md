# GPUv1-F08 · 将粗分辨率天气数据降尺度为区域集合场

Downscale coarse weather fields into regional ensembles

**组别**：科学机器学习与物理计算　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`corrdiff_taiwan_full_resolution_ensemble`

**Workflow family**：`regional_weather_downscaling`

## 任务目标

把台湾区域的一段粗分辨率气象输入转换为高分辨率概率场，交付逐时集合、均值/分位数，以及给定站点附近的风和降水相关场摘要。

## 具体来源工作负载

CorrDiff Taiwan模型；NGC corrdiff_inference_package:1的regression.mdlus与diffusion.mdlus；CWA完整Zarr源。

## 输入与配置

- NGC v1回归/扩散模型及其兼容配置
- 官方modulus_datasets_cwa:v1完整2023-01-24-cwb-4years.zarr中2021-09-10至2021-09-16逐小时输入
- 原生地理坐标、通道与归一化；可用的对应高分辨率目标用于科学评分

## 需要完成的工作

- 核对回归与扩散checkpoint配对及通道
- 执行原生区域网格上真实条件采样
- 生成连续168小时、每小时64成员的数值集合并分析空间/时间统计

## 交付物

- NetCDF input/truth/prediction组或等价有坐标Zarr
- 站点/区域摘要和集合分位数
- 逐时覆盖清单、采样设置与评分

## 后续使用与状态

按后续指定区域重新提取已有集合统计，并用已加载模型生成下一个真实小时；保留旧集合索引与模型状态。

## 独立验收

- 核对168小时和成员维度、原生地理网格及变量单位
- 重算均值/分位数和源score_samples对应评分，容差由参考版本校准
- 检查确实执行条件扩散，不能用插值或复制均值充当所有成员

## 应拒绝的失败方式

- 仅使用随权重包附带的5个小样本当正式规模
- 重复单个小时扩大数据量
- 只运行回归而跳过扩散
- 缺失小时静默删除

## 规模配方

### Debug：仅调通

- **workload**：NGC包附带的5时刻样本，检查软件和checkpoint兼容性。

### Reference large：正式生产规模

- **data**：官方CWA完整来源中2021-09-10T00:00到2021-09-16T23:00共168个不同小时，原始网格；构建时列举并检查每小时ID。
- **work**：每小时64个随机集合成员，使用对应版本官方扩散采样步数；完整写出和统计，不人为增加采样步数凑时长。
- **hardware_target**：T2：1×80GiB GPU分批采样；工程起始目标。

### 可选扩展：同一任务的变体

- **workload**：2–8 GPU按小时或成员分片；更长真实时段形成同ID规模配置。

## GPU工作与预期资源形态

固定真实区域天气场的条件扩散连续使用GPU，模型/激活驻留与分批输出覆盖计算和数据移动。

## 资源标签（待画像验证）

- diffusion_sampling
- large_spatial_tensors
- model_residency
- ensemble_output
- output_io

## 设备能力

- CUDA PyTorch
- compatible CorrDiff/Modulus or PhysicsNeMo checkpoint loader

## 后端要求

- 模型和非商业数据访问条件满足
- 足够输出和缓存空间
- 兼容老checkpoint的固定环境，禁用在线WandB等非任务依赖

## 回放约束

- 任务侧扩散采样真实执行，采样seed及步数冻结
- 源checkpoint配套旧代码与现代PhysicsNeMo不能直接混用；采集前完成格式兼容验证

## Builder需要实现的部分

- 验证完整CWA源的168小时可用性并hash；若缺小时须显式修订任务清单，不用重复填充
- 固定NGC模型和配套代码revision
- 实现NetCDF科学oracle与输出目录续写
- 校准数值容差与资源

## 与相关任务的边界

对同一时刻粗天气场补充区域细尺度不确定性，区别于未来全球天气滚动预测和极端事件mask分类。

## 数据血缘

- CWA/2023-01-24-cwb-4years.zarr
- ERA5/Taiwan-conditioning
- CorrDiff/NGC-v1

## 任务范围与条件

- 数据CC BY-NC-ND 4.0；checkpoint Apache-2.0，分开处理资产条件
- 选择时段属于来源年份，适合作系统任务，不构成独立泛化实验
- 168小时资产可用性需由builder正式核验

## 来源记录

- [F_CORRDIFF] PhysicsNeMo CorrDiff — [来源](https://github.com/NVIDIA/physicsnemo/blob/main/examples/weather/corrdiff/README.md)；检查位置：Taiwan dataset; sampling and evaluation; config_generate_taiwan.yaml
- [F_CORRDIFF_WEIGHTS] CorrDiff inference package v1 — [来源](https://catalog.ngc.nvidia.com/orgs/nvidia/modulus/models/corrdiff_inference_package/1)；检查位置：Version 1 overview; checkpoints and code compatibility hash

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
