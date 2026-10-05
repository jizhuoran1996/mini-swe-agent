# GPUv1-F04：完成催化吸附初态弛豫与能量排序

对给定催化表面吸附初态执行机器学习势弛豫，交付最终结构、能量、最大自由原子力与收敛状态，并按声明分组排序。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`source-native smaller catalyst checkpoint / exact declared relaxation recipe`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

OC20 IS2RE验证初态；EquiformerV2 153M All+MD检查点；main_oc20.py弛豫路径。

调试范围：{"workload": "每个验证分区各2个真实sid。"}

## 实际工作

- 加载同一势模型并校验单位与固定原子
- 以固定优化器、力阈值和最大步数运行实际弛豫
- 保存每个体系的最终几何与轨迹摘要；失败和未收敛均保留

## 交付物

- relaxed_structures.extxyz
- energies.parquet含sid/step/convergence
- 按吸附体系语义分组的排名与运行配置

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

从已保存的未收敛状态继续到声明总步数，并更新对应行；已经收敛的结构不能被重新随机初始化。

- 重载最终几何，在GPU上重算能量/力并检查单位和固定原子
- 核对每个sid输出完整、原子种类和周期边界未改变
- 收敛阈值及参考数值容差先校准；未收敛状态明确记录，不靠删行改善指标

禁止情况：

- 复制初态并伪造能量
- 用标签能量代替势计算
- 移动固定底层原子
- 只保留容易收敛的体系

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Actual source CUDA learned energy/forces for genuine OC20 IS2RE initial structures. Constrained atomic relaxation using source force threshold and max steps, atomic composition/cell/fixed atoms invariant. Save initial/final energies, forces, structures, optimizer trajectory/state. Resume further relaxation without reinitializing positions.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
