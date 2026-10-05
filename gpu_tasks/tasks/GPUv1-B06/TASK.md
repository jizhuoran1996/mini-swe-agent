# GPUv1-B06：训练驾驶场景三维目标检测并交付空间框

从 nuScenes 多次 LiDAR 扫描训练三维目标检测器，为完整验证场景交付包含位置、尺寸、朝向和速度的物体框，能够按场景和时间戳查询检测结果。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`source-native CenterPoint, single-scene debug`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

MMDetection3D CenterPoint configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py; nuScenes v1.0-trainval.

调试范围：{"data": "nuScenes mini 的完整场景", "schedule": "只用于数据与 CUDA 稀疏算子调试"}

## 实际工作

- 构建源格式数据索引，保留扫帧时间和坐标转换。
- 按源配置训练 CenterPoint 并保存优化器/模型状态。
- 对完整验证场景执行 3D 检测，转换到 nuScenes 输出格式并生成时间索引。

## 交付物

- CenterPoint checkpoint
- nuScenes detection JSON 与场景查询索引
- 有效配置和转换程序
- 重算检测指标与数据清单

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

用既有检测结果追查指定时段的物体空间轨迹，并用保存模型重新处理预先选定的完整验证场景，核对 token 和坐标一致性。

- 使用 nuScenes 格式检查 sample token、类别、translation、rotation、velocity 的合法性和覆盖。
- 从真实输出重算源检测指标，容差由参考运行校准。
- 抽样进行全局/车体/LiDAR 坐标往返检查，重推理选定场景。

禁止情况：

- 把局部坐标误当全局坐标
- 丢失 sweep/time 对齐
- 只输出二维框
- 复制 GT annotation 或跳过复杂场景

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Native MMEngine CUDA CenterPoint training, configurable one debug epoch on a genuine frozen scene list. Official box labels/class mapping and NMS. Persist checkpoint/optimizer and original nuScenes-format predictions; use tools/test.py to reload; resume extra epoch without relabeling.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
