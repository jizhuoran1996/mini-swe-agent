# GPUv1-A09 · 训练问答检索双编码器并交付检索表征

Train a question–passage dual encoder for retrieval

**组别**：语言、语音与推荐模型训练　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`dpr_nq_hard_negative_biencoder_training`

**Workflow family**：`dense_retrieval_training`

## 任务目标

使用真实问题、相关段落和困难负例训练问答检索模型，交付问题/段落编码器，并为冻结候选段落集合生成可用于后续检索的表征及验证排名。

## 具体来源工作负载

DPR biencoder_nq with nq_train+nq_train_hn1, nq_dev, BERT-base question/context encoders

## 输入与配置

- DPR data.retriever.nq 与 data.retriever.nq-adv-hn-train
- nq_dev和独立test问题；原始positive/hard-negative passage IDs
- DPR train=biencoder_nq；默认HuggingFace BERT-base双编码器

## 需要完成的工作

- 核对正例、困难负例和问题划分，保留去重与来源ID
- 按来源40-epoch训练协议执行双编码器更新，保存question/context encoder及optimizer
- 将固定验证候选池编码，生成每个问题的候选排名；使用准确点积评测以隔离ANN算法影响

## 交付物

- biencoder.pt及tokenizer/config
- passage_embeddings/与passage_id映射
- validation_rankings.jsonl、平均排名/Recall报告和训练清单

## 后续使用与状态

使用已训练的context encoder编码另一批冻结段落，并用question encoder处理后续问题；验证旧新向量维度和模型版本一致。

## 独立验收

- 重载两侧encoder，真实重算抽取的question/passage向量和点积分数
- 检查候选池、gold IDs和负例独立性，重新计算平均排名及Recall
- 校验训练更新和双侧权重完整性；质量容差按固定候选池参考执行确定
- 全量Wikipedia检索属于可选规模；不借用预计算原模型向量冒充本轮产物

## 应拒绝的失败方式

- 仅下载DPR checkpoint而没有训练
- 问题与段落来自不同checkpoint却拼接使用
- 交付FAISS索引或预存检索分数代替要求的训练后encoder

## 规模配方

### Debug：仅调通

- **data**：固定1,000个训练问题与100个验证问题的真实候选池
- **work**：相同BERT-base双编码器的数据与更新路径
- **hardware_target**：T1 1×24–48 GiB

### Reference large：正式生产规模

- **data**：完整nq_train+nq_train_hn1，完整nq_dev；验证候选池固定为其已发布positive/negative上下文去重全集
- **model**：来源biencoder_nq 40-epoch协议，维持声明有效batch和平均排名验证
- **output**：训练后双encoder、候选向量与排名
- **hardware_target**：T3 8×32–80 GiB，NCCL；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：来源dpr_wiki约21M段落全集
- **work**：本轮训练后的encoder实际生成全量向量，再评测NQ测试问题；与E组ANN任务不混记
- **hardware_target**：T3 4–8 GPUs，加声明的CPU内存/存储预算

## GPU工作与预期资源形态

问题与困难负例段落的双塔反向传播和批内相似度矩阵形成持续计算；后续大批量编码产生有用途的数据搬运和持久向量。

## 资源标签（待画像验证）

- contrastive_training
- dual_encoder
- hard_negatives
- all_reduce
- embedding_materialization
- checkpoint_io

## 设备能力

- CUDA
- NCCL
- declared mixed_precision

## 后端要求

- DPR归档版本的兼容软件镜像
- 统一模型hash贯穿训练、候选编码和后续查询

## 回放约束

- 训练和本轮embedding生成真实执行，预下载embedding不能替代
- 端口和rank绑定按本轮环境解析；数据依赖/平均排名阶段遵守实际完成事件

## Builder需要实现的部分

- 镜像化旧DPR依赖并检查公开数据可访问性
- 定义可验证的完整dev候选池和精确点积oracle
- 锁定数据顺序、负例抽样和参考数值容差

## 与相关任务的边界

本任务学习检索表征；D组使用已有模型提供embedding服务，E组处理ANN/索引算法，均不承担这里的本轮双encoder训练。

## 数据血缘

- natural_questions_dpr

## 任务范围与条件

- 代码CC-BY-NC 4.0，商业使用需另行核对许可
- 候选池评测不是全WikipediaRecall；两个规模的报告必须明确区分

## 来源记录

- [A_DPR] Dense Passage Retrieval official repository — [来源](https://github.com/facebookresearch/DPR)；检查位置：train_dense_encoder.py; biencoder_nq; nq_train+nq_train_hn1; nq_dev; BERT-base dual encoder; 40-epoch reference

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
