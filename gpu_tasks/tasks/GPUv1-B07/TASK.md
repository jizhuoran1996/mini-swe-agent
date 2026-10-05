# GPUv1-B07：训练点云语义分类并交付完整扫描标签

为 SemanticKITTI 的完整扫描训练点级语义分割器，对验证序列每个点生成与原始扫描顺序对应的标签文件，并交付按距离统计的语义覆盖报告。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`source-native Cylinder3D or explicitly labeled PointNet debug adapter`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

Cylinder3D official config/semantickitti.yaml and train.sh; SemanticKITTI single-scan semantic segmentation; official semantic-kitti-api evaluator.

调试范围：{"data": "源序列中固定少量完整扫描", "schedule": "仅验证稀疏算子、标签映射与输出对齐"}

## 实际工作

- 按官方 learning_map 训练，同时保留逆映射。
- 执行源训练配置声明的完整计划，保存最佳与最终 checkpoint。
- 对完整序列 08 推理，输出每个原始点的标签和距离分层报告。

## 交付物

- Cylinder3D checkpoint 与有效配置
- sequences/08/predictions/*.label
- 逐类与按距离 IoU 报告
- label 映射与批量预测入口

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

从保存模型继续处理声明的未标注序列，生成结构正确的标签包；已处理扫描的标签和索引必须保持可追溯。

- 核对每文件标签数等于原扫描点数，检查标签合法性与序列顺序。
- 应用官方逆映射后重算 mIoU 和距离分层指标，容差经参考校准。
- 不只依赖上游 submission 格式检查：额外拒绝全 ignored 或非法标签；抽样真实推理。

禁止情况：

- 输出体素标签但未映射回原始点
- 原始 ID 与训练 ID 混淆
- 用 ignored 类逃避误差
- 重复扫描或丢弃远处点

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Use actual official cylindrical voxelization and asymmetrical sparse network, true SemanticKITTI labels/map, native source training entry. Persist weights/optimizer/config, map logits back to every source point, save labels and progress. Reload inference for a new scan; ignore unannotated points properly.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
