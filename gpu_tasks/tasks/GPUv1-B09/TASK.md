# GPUv1-B09：训练单目标跟踪器并生成连续轨迹

训练一个只依赖首帧目标框的视觉跟踪器，在完整验证序列上连续跟踪指定物体，交付每帧边框、置信度与可独立运行的模型。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`OSTrack ViT-Base`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

OSTrack official GOT-10k config vitb_384_mae_ce_32x4_got10k_ep100; MAE ViT-Base initialization; GOT-10k train and validation.

调试范围：{"data": "固定少量完整真实训练/验证序列", "use": "检查采样、初始化和持续跟踪状态"}

## 实际工作

- 准备真实完整序列，区分首帧初始化和未来帧标注。
- 按 GOT-10k 专用 100-epoch 源配置训练并保存模型。
- 逐序列执行连续 GPU 跟踪，导出与帧一一对应的框与有效状态。

## 交付物

- OSTrack checkpoint 和配置
- 逐序列 boxes/confidence 文件
- 跟踪入口与初始化说明
- 完整验证覆盖及跟踪指标报告

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

使用持有的模型跟踪后续声明序列，或从合法首帧重新初始化某个长序列，输出完整轨迹并与原序列身份关联。

- 检查每序列只使用首帧框初始化，输出长度与帧清单一致，坐标合法。
- 按验证标注重算 overlap/success 指标，数值容差经参考训练校准。
- 抽样重跑完整短序列，检查结果由实际状态推进产生。

禁止情况：

- 每帧用 ground-truth 框重新初始化
- 复制首帧框到所有帧
- 丢弃遮挡或出视野帧
- 使用未来帧标签训练或调整预测

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Use native OSTrack ViT-Base initialization and GOT10k real videos with first-frame boxes. Adapt with real labels, checkpoint training state, run full sequence tracking, preserve every frame box and source ordering. Separate train/eval labels. Continuation processes a new sequence from checkpoint without rebuilding weights.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
