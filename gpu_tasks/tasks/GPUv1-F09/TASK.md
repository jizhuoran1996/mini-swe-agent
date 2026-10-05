# GPUv1-F09：训练车辆外流场代理并交付阻力预测

利用已有CFD样本建立车辆外流场代理，交付能从真实车体曲面网格预测压力、壁面剪切和阻力的模型，并给出留出车辆的数值场。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`source-native AeroGraphNet reduced genuine vehicle list`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

DrivAerNet v1约4000个车辆几何；PhysicsNeMo AeroGraphNet +experiment=drivaernet/agn。

调试范围：{"workload": "v1固定2训练/2验证车辆，原有网格预处理，仅做构建检查。"}

## 实际工作

- 建立稳定的网格节点/边与标签映射
- 训练AeroGraphNet并保存模型和数据统计
- 为整个官方test split生成.vtp数值场和阻力表

## 交付物

- 可重载AGN检查点
- predicted_fields/*.vtp
- drag_predictions.csv与留出集压力/剪切/阻力误差

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

重新载入模型，对声明的新几何批次生成预测并与先前目录合并；保留网格缓存，避免跨车辆节点映射混淆。

- 重读VTP，检查节点/几何和压力/剪切字段对应
- 独立加载模型对隐藏车辆真实推理并重算指标
- 检查划分无泄漏、阻力系数及单位/归一化；质量容差随固定参考预算校准

禁止情况：

- 只预测标量阻力而缺少要求的表面场
- 把Ahmed或新版++样本混入v1却不声明
- 删除复杂网格或只导出少量测试车
- 复制已有CFD标签当预测

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Native CUDA AeroGraphNet message passing on true DrivAerNet surface meshes and matching CFD pressure/shear labels. Train reduced genuine vehicle list, save model/optimizer/RNG/normalization, deliver predicted pressure on original mesh nodes, surface forces and heldout error. Reload for a new geometry, do not duplicate vehicles or invent CFD ground truth.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
