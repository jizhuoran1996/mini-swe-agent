# GPUv1-F07 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

为给定历史起报日期生成15天全球集合预报，交付可查询的气象场、集合均值/分位数和规定区域的风速与温度摘要。

### 来源和工作范围

NVIDIA FCN3官方NGC checkpoint；Earth2Studio FCN3 + NCAR_ERA5 + ensemble；0.25度、6小时步长。

### 交付要求

- forecast.zarr或NetCDF，包含init/member/lead/lat/lon/variable
- ensemble_statistics/
- 区域时间序列、评分及seed/权重manifest
- forecast_checkpoint/：完整模型推进状态与全部必需通道、各成员隐藏Markov/噪声状态和RNG状态、init/member/lead-time映射、批次进度，以及权重/配置/归一化引用和文件hash

### 必须完成的工作

- 离线核对ERA5坐标、变量和时间
- 执行32成员、60个6小时步的真实GPU预测，每个成员保留独立随机状态
- 写入NetCDF/Zarr并产生区域统计及与对应ERA5验证场的评分
- 在预报步边界保存可恢复的完整prognostic state：下一步所需全部气象通道与坐标、FCN3隐藏随机状态、每成员CPU/CUDA RNG状态及运行进度；五个对外交付气象量仅是分析输出。

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

从forecast_checkpoint重新加载一个给定起报的所有成员，恢复全部prognostic通道、FCN3隐藏随机状态、各成员RNG和时间进度，继续4个6小时步至后续24小时；追加坐标一致的五变量分析输出并更新摘要。不能仅凭五个导出气象量或重新设seed重启。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
