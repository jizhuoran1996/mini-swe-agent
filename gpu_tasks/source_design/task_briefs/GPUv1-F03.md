# GPUv1-F03 · 为长蛋白目标构建可复核的结构预测集

Produce a validated structure set for long protein targets

**组别**：科学机器学习与物理计算　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`openfold_casp14_long_target_structures`

**Workflow family**：`protein_structure_prediction`

## 任务目标

根据给定长蛋白序列和固定比对资料，生成完整结构、残基置信度和目标索引；提交可重新运行并重载结果的结构预测目录。

## 具体来源工作负载

OpenFold run_pretrained_openfold.py、model_1_ptm；CASP14 H1044、T1050、T1052、T1053、T1061。

## 输入与配置

- CASP14五个固定目标FASTA：H1044(2180残基)、T1050(779)、T1052(832)、T1053(580)、T1061(949)
- 固定版本OpenFold model_1_ptm兼容权重
- 预先冻结的MSA/模板命中和template date cutoff；native结构仅供验证

## 需要完成的工作

- 校验目标序列、MSA对应关系和完整长度
- 使用适合真实长链的chunk/offload策略执行GPU推理
- 交付完整结构与pLDDT/pTM等输出并完成基础几何检查

## 交付物

- 每个目标的PDB/mmCIF结构和置信度数组
- target_manifest.json
- 可复现推理配置及长链内存策略

## 后续使用与状态

对已预测结构提取声明残基区间和域间距离，保留并重用模型/对齐缓存；不能只交付短片段冒充全长预测。

## 独立验收

- 检查序列/残基编号映射和原子坐标完整性
- 重算与保密参考结构或固定参考运行的一致性指标，几何及数值容差在参考机校准
- 检查实际全长GPU推理和所选模板cutoff；输出置信度不能代替结构验证

## 应拒绝的失败方式

- 复制native结构
- 只预测短链或域后当作全长
- 返回已有PDB ID而无本次真实预测
- CPU比对耗时冒充GPU结构执行

## 规模配方

### Debug：仅调通

- **workload**：官方6KWC示例只检查软件和MSA格式。

### Reference large：正式生产规模

- **data**：上述5个真实目标全长，不重复序列、不添加填充；至少包括H1044完整2180残基链。
- **work**：以固定checkpoint和model_1_ptm配置生成每个目标的真实结构；低内存策略先于采集固定。
- **hardware_target**：T2：1×80GiB GPU，允许官方CPU offload并同时计主机成本。

### 可选扩展：同一任务的变体

- **workload**：2–4 GPU按目标分发；扩大到CASP14其他已公开长目标需生成同一任务的规模manifest，不增加任务ID。

## GPU工作与预期资源形态

长链Evoformer/pair表示和MSA状态提供真实大显存工作集与可能的主机设备交换；五个目标具有不同长度，不靠合成张量扩容。

## 资源标签（待画像验证）

- long_sequence
- large_pair_state
- cpu_gpu_offload
- model_residency
- variable_shape

## 设备能力

- CUDA PyTorch
- OpenFold compatible custom kernels
- BF16/TF32 only if pinned and validated

## 后端要求

- 兼容OpenFold的GPU/驱动/编译扩展
- 预置MSA及模板资源以明确CPU搜索边界
- 允许主机RAM支撑已声明offload

## 回放约束

- 结构模型是任务工具，推理必须真实执行，独立于agent决策LLM
- 等待CUDA完成后再读取结构文件；缓存和offload设置写入manifest

## Builder需要实现的部分

- 绑定并hash五个FASTA、MSA、native对应关系
- 冻结兼容权重/代码版本
- 实现序列、结构和数值容差验证
- 画像全长2180残基执行，不能以短示例代替

## 与相关任务的边界

输出蛋白三维结构，区别于分子动力学时间积分与催化吸附能量优化；不按不同蛋白目标另造多条任务ID。

## 数据血缘

- CASP14/H1044,T1050,T1052,T1053,T1061
- OpenFold/model_1_ptm

## 任务范围与条件

- MSA准备可能是独立且昂贵的CPU阶段
- 结构质量有领域不确定性，不能仅用pLDDT判功能正确
- 官方支持长链并不保证所有后端同样可用

## 来源记录

- [F_OPENFOLD] OpenFold Inference — [来源](https://openfold.readthedocs.io/en/latest/Inference.html)；检查位置：Precomputed alignments; config presets; outputs; long sequence inference
- [F_CASP14] CASP14 target list — [来源](https://predictioncenter.org/casp14/targetlist.cgi?view_targets=all)；检查位置：H1044, T1050, T1052, T1053, T1061 and linked sequence/native records

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
