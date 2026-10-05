# GPUv1-F07：生成全球天气集合预报及区域风险摘要

为给定历史起报日期生成15天全球集合预报，交付可查询的气象场、集合均值/分位数和规定区域的风速与温度摘要。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`source-native FCN3 two-member, two-step forecast`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

NVIDIA FCN3官方NGC checkpoint；Earth2Studio FCN3 + NCAR_ERA5 + ensemble；0.25度、6小时步长。

调试范围：{"workload": "一个源日期、2成员、2步，保持原生网格。"}

## 实际工作

- 离线核对ERA5坐标、变量和时间
- 执行32成员、60个6小时步的真实GPU预测，每个成员保留独立随机状态
- 写入NetCDF/Zarr并产生区域统计及与对应ERA5验证场的评分
- 在预报步边界保存可恢复的完整prognostic state：下一步所需全部气象通道与坐标、FCN3隐藏随机状态、每成员CPU/CUDA RNG状态及运行进度；五个对外交付气象量仅是分析输出。

## 交付物

- forecast.zarr或NetCDF，包含init/member/lead/lat/lon/variable
- ensemble_statistics/
- 区域时间序列、评分及seed/权重manifest
- forecast_checkpoint/：完整模型推进状态与全部必需通道、各成员隐藏Markov/噪声状态和RNG状态、init/member/lead-time映射、批次进度，以及权重/配置/归一化引用和文件hash

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

从forecast_checkpoint重新加载一个给定起报的所有成员，恢复全部prognostic通道、FCN3隐藏随机状态、各成员RNG和时间进度，继续4个6小时步至后续24小时；追加坐标一致的五变量分析输出并更新摘要。不能仅凭五个导出气象量或重新设seed重启。

- 重读全空间坐标和成员维度，确认没有缺时段/重复成员
- 由实际场重算集合统计及与ERA5的误差；随机数值容差由参考run校准
- 检查原生全球分辨率及全部模型状态真实演化，不能只算局部截图
- 在固定权重/配置和成员映射下，将重新加载checkpoint后的续报与不中断参考执行逐成员比较全部推进变量及隐藏状态；核对RNG恢复、时间连续和输出去重，数值容差预先校准。

禁止情况：

- 复制ERA5真值或重复单成员
- 将低分辨率插值场冒充0.25度模型计算
- 只返回绘图不交付可查询数值
- 预报继续时丢失成员随机状态

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Native Earth2Studio FCN3 pretrained CUDA, correct ordered full prognostic channel list at0.25degree,6-hour timestep,two members two steps debug. Save all restart fields, valid time, member IDs, RNG and config. Continue one more step from state; actual model and ERA5 initialization required. Regional hazard summary computed from predictions, not copied climatology.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
