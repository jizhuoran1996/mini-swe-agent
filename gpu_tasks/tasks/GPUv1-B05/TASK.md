# GPUv1-B05：生成三维肾脏肿瘤分割与体积结果

处理 KiTS19 声明的完整三维 CT 病例集，生成肾脏与肿瘤的体积分割，恢复每例的空间信息，并交付可由下游程序读取的分割体和体积统计。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`source-native 3D U-Net`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

MLPerf Inference KiTS19 3D U-Net PyTorch CUDA workload; official 42-case accuracy set and matching reference model/preprocessing.

调试范围：{"data": "2 个真实源病例的完整体积", "use": "核查三维预处理、空间还原和 oracle；不作为 formal-full"}

## 实际工作

- 核对每例 CT 几何和输入规范，生成声明的预处理数据。
- 在 GPU 上执行全部病例的真实三维分割，处理完整体而不是少数二维切片。
- 恢复输出到声明空间，计算每类体积并交付 case-level 清单。

## 交付物

- 每例 NIfTI 或明确声明的体素数组及 affine/spacing sidecar
- kidney/tumor volume CSV
- 可重载推理入口
- 病例覆盖、模型和配置 manifest

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

在保留模型的后续工具调用中，重访指定病例并导出指定切面及连通区域摘要；统计必须与已交付体分割一致。

- 检查 42 例准确覆盖、体素数、标签集合、spacing 与方向；结果必须能独立读取。
- 使用 oracle 标签重算每例/总体 Dice，容差由同精度参考推理校准，不能直接复制官方分数。
- 从真实输出体素和 spacing 重算体积，抽样重推理检查结果对应病例。

禁止情况：

- 仅处理一张切片或中心裁剪冒充完整病例
- 输出空/全前景 mask
- 丢失空间信息导致体积错误
- 评测器代替 agent 运行完整分割

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Reference torchscript model and officially preprocessed true 3D CT cases. CUDA sliding window 128^3, overlap0.5, exact preprocessing/model binding from cases.json. Save original-shape three-class masks, case manifests and progress; resume completed cases; new case inference reloads the same reference model. Do not infer model architecture from arbitrary shape or substitute random UNet.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
