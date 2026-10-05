# GPUv1-A07 · 训练并交付大表嵌入的点击率模型

Train and deliver a large-embedding click-through-rate model

**组别**：语言、语音与推荐模型训练　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`dlrm_criteo_terabyte_fl3_training`

**Workflow family**：`recommendation_ranking_training`

## 任务目标

用完整点击日志训练能够对新曝光记录打分的推荐模型，交付嵌入表、数值特征配置、模型参数及独立测试评分，确保另一个进程可恢复同样的特征语义。

## 具体来源工作负载

NVIDIA DLRM PyTorch, Criteo Terabyte, frequency threshold FL=3 large configuration

## 输入与配置

- Criteo Terabyte day_0..day_22训练，day_23按官方前后半测试/验证
- 来源FL=3预处理结果与FeatureSpec；不使用synthetic_dataset
- NVIDIA DLRM混合并行large配置，完整一轮训练

## 需要完成的工作

- 核对训练数据分割、真实类别映射、频率阈值和数值特征dtype
- 执行稀疏嵌入更新和dense MLP训练，保存所有rank上的模型状态
- 重新加载模型并对声明的测试曝光输出概率，独立计算ROC-AUC和logloss

## 交付物

- model/：各rank嵌入与MLP checkpoint
- feature_spec.yaml及类别映射摘要hash
- prediction shards、sample-ID清单与可复算测试报告

## 后续使用与状态

加载已保存的大嵌入模型，对另一块固定测试曝光执行批量评分；验证不同工具调用仍使用同一类别映射和模型版本。

## 独立验收

- 按FeatureSpec真实重建并加载模型，验证所有嵌入分片齐全
- 测试sample IDs完整，概率有限且与重算结果在校准容差内
- ROC-AUC/logloss独立计算；训练进度覆盖day_0..22一轮
- 检查稀有类别处理和train/test边界，不能通过缩小类别空间冒充FL=3

## 应拒绝的失败方式

- 用随机或synthetic数据代替真实Criteo
- 只保留小部分embedding表或漏掉rank分片
- 复制来源AUC而没有本轮可复算预测

## 规模配方

### Debug：仅调通

- **data**：来自真实day_0的固定互异记录子集及独立测试块
- **work**：FeatureSpec、分片、保存和重载通路检查；较小类别域仅属debug
- **hardware_target**：T1 1×24–48 GiB

### Reference large：正式生产规模

- **data**：完整来源FL=3 Criteo预处理集合，官方天级切分，一轮训练
- **model**：DLRM large；来源描述约82GB checkpoint量级，实际显存需重测
- **output**：大嵌入推荐模型和全量声明测试评分
- **hardware_target**：T3 8×40–80 GiB，NCCL all-to-all；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：同一真实Criteo数据，来源FL=2 xlarge为独立规模配置
- **work**：较低类别频率过滤保留更多真实稀有类别，仍是同一语义任务
- **hardware_target**：T3 8×80 GiB；须冻结不同预处理版本，不将规模当新任务

## GPU工作与预期资源形态

真实类别基数产生大规模嵌入状态；稀疏访问与dense计算以及跨GPU all-to-all共同覆盖单一Transformer训练没有的资源路径。

## 资源标签（待画像验证）

- embedding_memory
- sparse_updates
- all_to_all
- hybrid_parallelism
- large_checkpoint
- input_streaming

## 设备能力

- CUDA
- FP16/declared TF32
- NCCL all-to-all
- peer communication

## 后端要求

- 同一任务的多个GPU共同准入，支持rank间collectives
- 声明NUMA/CPU绑定、共享内存和数百GB训练资产路径

## 回放约束

- 预处理是固定初始资产或实际工具阶段二选一并冻结；不能不同后端混用边界
- 通信完成、各rank保存完成后才发布模型；rank失败保留为失败

## Builder需要实现的部分

- 获取并核对Criteo授权与原始天级数据
- 制作FL=3固定资产和可运行版本镜像
- 适配多rank模型重载验证与GPU/网络/宿主成本计量

## 与相关任务的边界

预测广告点击的结构化分类工作流，稀疏表分布与NLP/语音模型不同；数据处理类E任务不替代这里的本轮模型训练。

## 数据血缘

- criteo_terabyte

## 任务范围与条件

- 采用有明确实现和模型规模的NVIDIA DLRM，不冒称当前MLPerf DLRMv2协议
- 来源模型/内存大小为上游描述，THENAME资源用量尚未实测

## 来源记录

- [A_DLRM] NVIDIA DLRM for PyTorch — [来源](https://github.com/NVIDIA/DeepLearningExamples/blob/master/PyTorch/Recommendation/DLRM/README.md)；检查位置：Criteo day_0..day_22 training; day_23 split; FL=3 large model; one epoch; hybrid parallel all-to-all; test-only reload

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
