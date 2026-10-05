# GPUv1-F07 · 生成全球天气集合预报及区域风险摘要

Generate a global weather ensemble and regional summaries

**组别**：科学机器学习与物理计算　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`fcn3_era5_15day_ensemble`

**Workflow family**：`global_ensemble_weather_forecast`

## 任务目标

为给定历史起报日期生成15天全球集合预报，交付可查询的气象场、集合均值/分位数和规定区域的风速与温度摘要。

## 具体来源工作负载

NVIDIA FCN3官方NGC checkpoint；Earth2Studio FCN3 + NCAR_ERA5 + ensemble；0.25度、6小时步长。

## 输入与配置

- FCN3默认发布权重的固定下载版本及hash
- ERA5 2020-02-11、2020-06-01、2020-09-01、2020-12-01 00UTC初场
- 发布模型要求的全部输入变量和归一化；声明输出u10m/v10m/t2m/msl/tcwv

## 需要完成的工作

- 离线核对ERA5坐标、变量和时间
- 执行32成员、60个6小时步的真实GPU预测，每个成员保留独立随机状态
- 写入NetCDF/Zarr并产生区域统计及与对应ERA5验证场的评分
- 在预报步边界保存可恢复的完整prognostic state：下一步所需全部气象通道与坐标、FCN3隐藏随机状态、每成员CPU/CUDA RNG状态及运行进度；五个对外交付气象量仅是分析输出。

## 交付物

- forecast.zarr或NetCDF，包含init/member/lead/lat/lon/variable
- ensemble_statistics/
- 区域时间序列、评分及seed/权重manifest
- forecast_checkpoint/：完整模型推进状态与全部必需通道、各成员隐藏Markov/噪声状态和RNG状态、init/member/lead-time映射、批次进度，以及权重/配置/归一化引用和文件hash

## 后续使用与状态

从forecast_checkpoint重新加载一个给定起报的所有成员，恢复全部prognostic通道、FCN3隐藏随机状态、各成员RNG和时间进度，继续4个6小时步至后续24小时；追加坐标一致的五变量分析输出并更新摘要。不能仅凭五个导出气象量或重新设seed重启。

## 独立验收

- 重读全空间坐标和成员维度，确认没有缺时段/重复成员
- 由实际场重算集合统计及与ERA5的误差；随机数值容差由参考run校准
- 检查原生全球分辨率及全部模型状态真实演化，不能只算局部截图
- 在固定权重/配置和成员映射下，将重新加载checkpoint后的续报与不中断参考执行逐成员比较全部推进变量及隐藏状态；核对RNG恢复、时间连续和输出去重，数值容差预先校准。

## 应拒绝的失败方式

- 复制ERA5真值或重复单成员
- 将低分辨率插值场冒充0.25度模型计算
- 只返回绘图不交付可查询数值
- 预报继续时丢失成员随机状态

## 规模配方

### Debug：仅调通

- **workload**：一个源日期、2成员、2步，保持原生网格。

### Reference large：正式生产规模

- **data**：4个固定真实ERA5初场；模型原生全球0.25度网格；输出5个声明气象量。
- **work**：每个初场32个不同集合成员，各15天共60步；生成128条物理预报轨迹及数值产物，不重复媒体或输入。
- **hardware_target**：T2：1×80GiB GPU，按成员批次运行；T3可分配独立成员。

### 可选扩展：同一任务的变体

- **workload**：2–8 GPU分配集合成员或日期；扩大历史日期集和集合宽度仍为同一科学预报任务。

## GPU工作与预期资源形态

完整全球多变量状态持续在设备演化，球面卷积和集合随机状态产生显存驻留、计算和大结果写出。

## 资源标签（待画像验证）

- autoregressive_forecast
- large_spatial_state
- ensemble_work
- model_residency
- output_io

## 设备能力

- CUDA PyTorch
- torch-harmonics CUDA extensions
- FCN3 compatible BF16

## 后端要求

- 初场/权重离线可用
- 足够输出空间及固定压缩/chunk策略
- 保留集合成员状态和模型的session

## 回放约束

- 气象模型是实际GPU工具，不是被模拟的agent LLM
- 等待期间如果预测进程仍运行，应保留后台活动；应用forecast checkpoint不代表GPU上下文可快照
- 分析输出与续报checkpoint分开；seed不能代替推进到保存时刻后的RNG/隐藏状态。成员分片、批次和设备绑定要能明确映射，异步GPU工作完成后再原子保存状态。

## Builder需要实现的部分

- 固定ERA5下载与FCN3包revision
- 绑定原生坐标和变量映射
- 实现NetCDF/Zarr完整性与科学统计oracle
- 实现并验证FCN3完整prognostic/隐藏Markov状态、每成员CPU/CUDA RNG及进度的序列化和重载；用分段执行对照不中断执行测试，而非假定通用Earth2Studio输出已足够续报

## 与相关任务的边界

输出未来时间序列的全球概率预报；DeepCAM是事件分类，CorrDiff是同一时刻粗到细空间降尺度。

## 数据血缘

- ERA5/2020-selected-initializations
- FCN3/NGC-default-checkpoint

## 任务范围与条件

- 历史预报用于系统任务，不能宣称新的预测精度结果
- 大量场输出可能成为I/O瓶颈，应画像而非隐去
- FCN3 checkpoint/ERA5使用条件需在构建时固定

## 来源记录

- [F_FCN3] FourCastNet 3: large ensemble weather forecasting — [来源](https://developer.nvidia.com/blog/fourcastnet-3-enables-fast-and-accurate-large-ensemble-weather-forecasting-with-scalable-geometric-ml/)；检查位置：Getting started with FCN3; NCAR_ERA5; NetCDF4 ensemble example
- [F_EARTH2_ENSEMBLE] Earth2Studio ensemble workflow — [来源](https://nvidia.github.io/earth2studio/main/examples/01_getting_started/03_ensemble_workflow/)；检查位置：Ensemble batching; output coordinates; checkpointed workflow

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
