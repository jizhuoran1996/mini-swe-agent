# GPUv1-F06：模拟金属晶体并分析有限温度结构稳定性

使用给定SNAP势推进有限温度BCC钽晶体，交付可续跑的原子状态、能量漂移和径向分布报告，确认计算期间的结构行为。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`source-native LAMMPS SNAP Ta nrep=4 short GPU run`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

LAMMPS examples/snap/in.snap.Ta06A；potentials/Ta06A.snap、Ta06A.snapcoeff、Ta06A.snapparam；Kokkos GPU。

调试范围：{"workload": "官方nrep=4、100步示例，仅作构建检查。"}

## 实际工作

- 从官方晶格规则建立声明空间域并保存初态
- 通过Kokkos GPU进行NVE时间积分
- 输出规定频率的能量、原子轨迹和restart，计算RDF/结构统计

## 交付物

- initial.data和final.restart
- thermo.csv、trajectory文件和RDF结果
- 实际势/积分/邻域参数及构建信息

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

从final.restart接着积分5ps，再生成新增区间的统计；要求保留速度、盒和势配置。

- 核对原子数、盒长、势文件hash及正确的单位/时间覆盖
- 在保存帧上独立重算RDF、能量和简单结构统计
- 能量漂移/初期力的数值容差基于固定参考确定；不用CPU/GPU长轨迹逐bit相等

禁止情况：

- 只生成晶格而不积分
- 用解析曲线替代本次RDF
- 删除SNAP或ZBL相互作用
- 反复复制轨迹帧或以空循环冒充物理时间

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Native tantalum SNAP, nrep=4, real Kokkos CUDA binary built for RTX5090 sm120, run100steps plus50step restart. Never substitute Lennard-Jones or CPU lmp. Verify binary -h lists KOKKOS CUDA/snap/kk; require execution log to prove actual GPU backend. Save restart, thermo quantities, full per-atom trajectory and used input/potential hashes. Upstream files may be copied into bounded workspace to adjust run/dump/restart without modifying source.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
