# GPUv1-F08：将粗分辨率天气数据降尺度为区域集合场

把台湾区域的一段粗分辨率气象输入转换为高分辨率概率场，交付逐时集合、均值/分位数，以及给定站点附近的风和降水相关场摘要。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`source-native CorrDiff five-sample inference`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

CorrDiff Taiwan模型；NGC corrdiff_inference_package:1的regression.mdlus与diffusion.mdlus；CWA完整Zarr源。

调试范围：{"workload": "NGC包附带的5时刻样本，检查软件和checkpoint兼容性。"}

## 实际工作

- 核对回归与扩散checkpoint配对及通道
- 执行原生区域网格上真实条件采样
- 生成连续168小时、每小时64成员的数值集合并分析空间/时间统计

## 交付物

- NetCDF input/truth/prediction组或等价有坐标Zarr
- 站点/区域摘要和集合分位数
- 逐时覆盖清单、采样设置与评分

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

按后续指定区域重新提取已有集合统计，并用已加载模型生成下一个真实小时；保留旧集合索引与模型状态。

- 核对168小时和成员维度、原生地理网格及变量单位
- 重算均值/分位数和源score_samples对应评分，容差由参考版本校准
- 检查确实执行条件扩散，不能用插值或复制均值充当所有成员

禁止情况：

- 仅使用随权重包附带的5个小样本当正式规模
- 重复单个小时扩大数据量
- 只运行回归而跳过扩散
- 缺失小时静默删除

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Actual source regression+conditional diffusion CUDA on genuine CWA low/highresolution grids, five samples. Preserve channel ordering, normalization, time and spatial georeference, probabilistic ensemble and per-sample seeds. Persist output/state and allow additional samples for a new time from the same checkpoints. Do not use upsampled ERA5 or ordinary UNet as CorrDiff.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
