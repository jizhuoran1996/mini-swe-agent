# GPUv1-F03：为长蛋白目标构建可复核的结构预测集

根据给定长蛋白序列和固定比对资料，生成完整结构、残基置信度和目标索引；提交可重新运行并重载结果的结构预测目录。

本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`ESMFold single-chain debug alternative without the OpenFold database requirement`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。

## 来源及范围

OpenFold run_pretrained_openfold.py、model_1_ptm；CASP14 H1044、T1050、T1052、T1053、T1061。

调试范围：{"workload": "官方6KWC示例只检查软件和MSA格式。"}

## 实际工作

- 校验目标序列、MSA对应关系和完整长度
- 使用适合真实长链的chunk/offload策略执行GPU推理
- 交付完整结构与pLDDT/pTM等输出并完成基础几何检查

## 交付物

- 每个目标的PDB/mmCIF结构和置信度数组
- target_manifest.json
- 可复现推理配置及长链内存策略

统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。

## 后续使用和独立验收

对已预测结构提取声明残基区间和域间距离，保留并重用模型/对齐缓存；不能只交付短片段冒充全长预测。

- 检查序列/残基编号映射和原子坐标完整性
- 重算与保密参考结构或固定参考运行的一致性指标，几何及数值容差在参考机校准
- 检查实际全长GPU推理和所选模板cutoff；输出置信度不能代替结构验证

禁止情况：

- 复制native结构
- 只预测短链或域后当作全长
- 返回已有PDB ID而无本次真实预测
- CPU比对耗时冒充GPU结构执行

## 测试环境

工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。

请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。


当前实施约束：
Native OpenFold CUDA structure inference with actual sequence/MSA/template features and model_1_ptm. Deliver PDB per target with residue identifiers/pLDDT and provenance, source config and feature binding. New FASTA processing must run the same checkpoint; no copied experimental PDB as prediction.
只读input中所需文件详见manifest。实现完整source-native适配器，入口 run --input input --output output、resume（若有状态）与doctor --input input；doctor必须列出所有缺失文件/软件并exit78。未准入资产不准造假、下载、CPU替代或报告任务通过。main --help与源码编译是基础可用性检查。
