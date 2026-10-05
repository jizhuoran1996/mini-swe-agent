# GPUv1-D08 · 为百万级多语言语料生产可更新的语义向量

Produce updateable semantic embeddings for multilingual corpora

**组别**：任务侧模型推理与检索处理　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`miracl_ar_hi_full_embeddings_service`

**Workflow family**：`large_corpus_embedding`

## 任务目标

将给定阿拉伯语和印地语语料转为带稳定文档 ID 的语义向量分片，部署查询嵌入接口，并在后续调用中继续处理剩余分片和新查询。

## 具体来源工作负载

MIRACL ar 与 hi 全部段落及 dev 查询；Qwen/Qwen3-Embedding-8B，4,096 维输出

## 输入与配置

- MIRACL ar 2,061,414 段落、hi 506,264 段落及对应 dev queries/qrels
- Qwen3-Embedding-8B 官方权重与 tokenizer
- 固定标题/正文拼接、查询 instruction、pooling、normalization 和向量 dtype

## 需要完成的工作

- 建立文档 ID 到向量行的双向映射
- 对全部实际文本在 GPU 上执行模型前向，分片保存向量
- 部署查询编码接口，输出 dev 查询向量与小型固定检索探针的结果
- 交付实际可启动的 multilingual_embedding_service 服务；实现 POST /v1/embeddings 的请求/响应 schema，并输出本轮逻辑服务绑定。

## 交付物

- embeddings/shard-*.safetensors
- row_to_docid.parquet
- query_embeddings.safetensors
- embedding_service_config.json
- service/serve.py 与 service/launcher.json（可启动的模型服务入口）
- service/request_schema.json、response_schema.json 与 model_config.json
- service/service_binding.json（逻辑服务到本轮 endpoint/模型进程/设备的绑定）
- requests/initial.jsonl、requests/continuation.jsonl 与在线响应/完成事件记录

## 后续使用与状态

模型保持加载时接收后续查询；对 manifest 预留的语料分片追加编码并更新索引清单，不重新编码已提交分片。；具体后续请求来自 requests/continuation.jsonl，在 recorded wait 后通过本轮逻辑服务绑定真实提交并验收。

## 独立验收

- 检查所有源 ID 覆盖、向量维度/dtype/有限性以及行映射
- 抽取原始文本在 GPU 上重新编码，按参考浮点容差比较向量；不能只校验文件哈希
- 对封存相关性探针重新计算距离及排序并检查合理质量，主体不建设 ANN 索引
- recorded wait 后，向本轮仍加载模型的 embedding endpoint 发送冻结留出 dev 查询，验证在线返回的 4096 维向量、输入 ID、模型哈希及当前 GPU 前向；离线文档向量文件和 /healthz 不能替代在线验收。

## 应拒绝的失败方式

- 随机向量或全零向量
- 复制同一段文本多次凑 corpus 大小
- 只生成查询向量但没有全量文档向量
- 丢失语言或文档 ID 对应关系
- 离线文件通过但线上模型服务不可用，或在线请求只查旧答案缓存却没有本轮模型工作

## 规模配方

### Debug：仅调通

- **data**：每语言稳定取 1,000 个真实段落与 20 查询
- **hardware_target**：T1：单 24–48 GiB GPU；不作为正式大规模结果

### Reference large：正式生产规模

- **data**：ar+hi 完整语料共 2,567,678 个原始段落与对应 dev 查询
- **model**：Qwen3-Embedding-8B，BF16 前向，4,096 维；输出 dtype 在 manifest 冻结
- **hardware_target**：T1：单 48 GiB GPU，充足主存和向量输出盘；可持续运行，时间待画像
- **useful_output**：百万级可读向量分片与真实查询编码服务

### 可选扩展：同一任务的变体

- **data**：加入 MIRACL en 全 32,893,221 段落作为同一任务的 corpus scale；必须更新 manifest
- **hardware_target**：T3：2–8 GPU 数据分片并行，无强制 collective
- **not_new_task**：True

## GPU工作与预期资源形态

8B 参数虽小于生成模型，但数百万不同文本产生持续有效前向和大型向量输出，覆盖权重驻留、token 化、H2D 与 D2H。

## 资源标签（待画像验证）

- sustained_forward
- weight_residency
- corpus_streaming
- large_d2h_output
- append_only_state

## 设备能力

- CUDA
- BF16

## 后端要求

- 被测 sandbox 能访问声明的 GPU 设备与匹配的 CUDA/driver 用户态库；正式运行不静默转 CPU 或远程模型 API。
- 初始模型和输入在声明的只读路径，产物写入本 session 工作区；驱动兼容性与单/多 GPU 能力准入独立于功能验收。

## 回放约束

- 替换的仅是负责决策的 agent LLM；本任务载入的模型及其 prefill、decode、embedding 或 reranking 每次都真实执行，不返回旧预测冒充执行。
- 冻结模型/数据内容哈希、tokenizer/processor、dtype、算子后端、解码及分片参数；服务端口和作业 ID 在本轮绑定，不能复用旧句柄。
- 工具完成以 CUDA 工作与输出提交完成为准；记录的模型等待不替代服务 ready、CUDA event 或文件落盘依赖。
- 所有正式请求先在同一 manifest 中分成互斥 initial 与 continuation ID 列表；全量规模是两者并集，每个来源请求只计一次。留出 continuation 请求在 recorded model wait 结束后真实提交；没有录到等待时不人为补 sleep。额外重算/重复请求另记 attempt/repeat，不增加独立样本数。

## Builder需要实现的部分

- 固定 MIRACL 语言快照、段落 ID 与 tokenizer/池化实现
- 构建分片原子提交、恢复与向量重算 oracle
- 记录真实文本/token 总量，不用最大长度填充估计工作量
- 实现 launcher、健康与 /v1/embeddings 推理协议；把冻结留出请求在记录等待后经本轮 binding 发给实际模型进程，并关联响应与设备事件。

## 与相关任务的边界

生产神经语义表示；E 组 ANN 任务接收既有向量并构建/搜索索引，算法和主要输入不同。

## 数据血缘

- miracl_ar_hi

## 任务范围与条件

- 全语料运行可能较长，不能把 debug 子集速度当作正式完成时间。
- dev 全量检索若需要 ANN，应声明为另外的下游模块，不暗中移动到 grader。

## 来源记录

- [D_MIRACL] MIRACL corpora and relevance judgments — [来源](https://github.com/project-miracl/miracl)；检查位置：Corpora table: ar 2,061,414 passages, hi 506,264; dev queries and relevance judgments
- [D_QWENEMB8] Qwen3-Embedding-8B model card — [来源](https://huggingface.co/Qwen/Qwen3-Embedding-8B)；检查位置：Model overview and local SentenceTransformers/Transformers inference; last-token pooling; output dimension

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
