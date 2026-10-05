# GPUv1-A10 · 从完整百科语料训练通用文本编码器

Pretrain a general text encoder on a full encyclopedia corpus

**组别**：语言、语音与推荐模型训练　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`bert_large_wikipedia_20231101_pretraining`

**Workflow family**：`masked_language_encoder_pretraining`

## 任务目标

用固定英文百科快照训练通用文本表示模型，交付编码器、词表和可恢复训练状态，并在独立文档上完成掩码预测与句子表示导出。

## 具体来源工作负载

NVIDIA BERT large two-phase pretraining + Wikimedia Wikipedia 20231101.en

## 输入与配置

- wikimedia/wikipedia config 20231101.en 的全量文章快照，按article_id确定性划出保留集
- NVIDIA BERT bert_configs/large.json与固定WordPiece词表
- dgxa100-80g_8gpu_fp16来源两阶段配置：128-token phase1 7038 updates、512-token phase2 1563 updates

## 需要完成的工作

- 按文章边界构建预训练数据和固定masked targets，保留article IDs和token覆盖清单
- 从声明随机初始化运行来源LAMB两阶段训练，真实更新参数并保存最终及可恢复状态
- 重载encoder对保留文章计算masked-token NLL/accuracy，导出一组真实句子表示

## 交付物

- bert_encoder.pt、large.json、vocab.txt
- optimizer_and_progress/与预训练数据manifest
- heldout_mlm_predictions、sentence_embeddings及可复算评测报告

## 后续使用与状态

使用已交付encoder处理新的冻结文档批次，输出句子表示和掩码预测，复用训练完成后的模型状态。

## 独立验收

- 检查24层large模型结构和完整词表、真实训练权重及进度
- 重建固定mask的保留输入并独立计算NLL/accuracy，与参考校准范围比较
- 验证训练/保留文章严格分离；向量非恒定且可由本轮模型重算
- 训练预算和数据读取量与manifest对应，不能把只有benchmark计时循环的run当作交付

## 应拒绝的失败方式

- 提交公开预训练checkpoint而非本轮训练结果
- 只跑少量warmup batch后报全量训练
- 重复一段文本或零token填充来维持GPU忙碌

## 规模配方

### Debug：仅调通

- **data**：20231101.en固定10,000个互异文章和独立100篇保留文档
- **work**：同一large架构、预处理和checkpoint通路的小预算检查
- **hardware_target**：T1 1×48 GiB或T2 1×80 GiB

### Reference large：正式生产规模

- **data**：完整20231101.en文章库扣除固定article-ID保留集，约6.4M文章的来源规模
- **model**：BERT-large来源两阶段结构和更新预算7038+1563；语料版本为THENAME派生替换
- **output**：实际训练出的encoder、优化器状态和保留集预测/表征
- **hardware_target**：T3 8×80 GiB，NCCL；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：同一语料及固定目标token预算
- **work**：多节点或GPU布局改变作为场景；不以额外epochs凑独立任务
- **hardware_target**：T3 8 GPUs为标准，大于8另行声明

## GPU工作与预期资源形态

密集encoder从头训练的优化器状态、128到512token阶段切换和集体通信覆盖完整GPU训练作业生命周期，区别于只加载模型做预测。

## 资源标签（待画像验证）

- dense_pretraining
- phase_change
- optimizer_state
- all_reduce
- checkpoint_io
- data_preprocessing

## 设备能力

- CUDA
- FP16
- NCCL
- compatible fused LAMB kernels

## 后端要求

- 冻结NVIDIA训练实现及LDDL/APEX依赖，不默认要求Docker-in-Docker
- 明确预处理在准备阶段还是工具阶段，记录宿主RAM和存储成本

## 回放约束

- 从phase1到phase2的训练状态依赖真实checkpoint完成，不能以sleep模拟训练
- 两个backend使用相同mask、文章次序和更新预算；数值差异用校准容差验证

## Builder需要实现的部分

- 将固定Wikipedia parquet导出为保留文档边界的来源预处理输入
- 构建兼容的large两阶段训练镜像和有效随机初始状态
- 校准训练收敛与指标容差、采集完整轨迹并测量资源

## 与相关任务的边界

目标为从无标注文本训练双向encoder，输出掩码预测和表征；不是A01指令SFT、A02偏好优化或A09有标签检索训练的参数变体。

## 数据血缘

- wikipedia_20231101_en

## 任务范围与条件

- 当前语料替换了历史训练语料，不宣称复现MLPerf BERT或原NVIDIA质量分数
- 训练成本可能较大；采用来源实际训练预算，不能按不同后端速度提前截断

## 来源记录

- [A_BERT] NVIDIA BERT for PyTorch — [来源](https://github.com/NVIDIA/DeepLearningExamples/blob/master/PyTorch/LanguageModeling/BERT/README.md)；检查位置：BERT large configuration; Wikipedia preprocessing; 128/512-token phases; scripts/configs/pretrain_config.sh dgxa100-80g_8gpu_fp16
- [A_WIKIPEDIA] Wikimedia Wikipedia dataset — [来源](https://huggingface.co/datasets/wikimedia/wikipedia)；检查位置：20231101.en snapshot, approximately 6.4 million full articles, document IDs and text

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
