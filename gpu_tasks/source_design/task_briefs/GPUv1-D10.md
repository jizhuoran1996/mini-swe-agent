# GPUv1-D10 · 交付多语言文档翻译包并提供后续翻译接口

Deliver multilingual document translations and a continuation service

**组别**：任务侧模型推理与检索处理　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`wmt24pp_eight_languages_translation_archive`

**Workflow family**：`multilingual_document_translation`

## 任务目标

将英文来源文档翻译成指定八种语言，保持 document_id/segment_id 与段落顺序，交付逐语言翻译文件，并提供可继续处理其他原始段落的本地 GPU 接口。

## 具体来源工作负载

google/wmt24pp 的 en-de_DE、en-fr_FR、en-es_MX、en-it_IT、en-ja_JP、en-ko_KR、en-zh_CN、en-ru_RU 全部有效行；CohereLabs/aya-expanse-32b

## 输入与配置

- WMT24++ 上述八个具名语言对；仅 source 与文档标识交给生成器
- is_bad_source=true 行按来源建议在冻结 manifest 前排除
- Aya Expanse 32B 权重、tokenizer 和固定翻译提示；target/original_target 只给验证器

## 需要完成的工作

- 按文档和语言整理来源段落，不跨文档拼接
- 加载多语言模型实际生成各目标语言译文
- 保持逐段对齐、文档顺序与未完成记录，生成按语言分目录的翻译包

## 交付物

- translations/<language>.jsonl
- documents/<language>/*.txt
- segment_manifest.json
- translation_service_config.json

## 后续使用与状态

在模型保留的 session 中处理 manifest 预留的后续文档，更新翻译目录而不覆盖原译文，并对用户指定文档导出整篇文本。

## 独立验收

- 检查每个有效语言对/segment ID 恰好一条译文与文档顺序
- 用固定版本 chrF/BLEU 等非生成式评分对官方 post-edit target 复算，质量阈值参考运行校准
- 检查空输出、源文复制、语言混用及实际当前服务响应

## 应拒绝的失败方式

- 用公开 target 列填充交付物
- 只翻译一种语言后复制到其他目录
- 重复源段落凑数量或改变目标语言定义

## 规模配方

### Debug：仅调通

- **data**：每种语言选 2 个完整来源文档
- **hardware_target**：T2：单 80 GiB GPU

### Reference large：正式生产规模

- **data**：八个具名 WMT24++ 配置的全部非 bad-source 行；每行翻译一次，确切 ID 列表在建包时冻结
- **model**：CohereLabs/aya-expanse-32b，BF16；整文档段落结构保留，冻结提示和解码
- **hardware_target**：T2：单 80 GiB GPU
- **useful_output**：八语言文档翻译档案与可继续调用服务

### 可选扩展：同一任务的变体

- **data**：同一八语言语料按文档分片；更多模型支持的 WMT24++ 语言属于同任务 scale
- **hardware_target**：T3：2–4 GPU 模型副本
- **not_new_task**：True

## GPU工作与预期资源形态

32B 多语言模型在大量不同来源段落上连续生成，保留权重和文档上下文，输出是实际可消费的翻译文件。

## 资源标签（待画像验证）

- weight_residency
- sustained_decode
- multilingual_tokenization
- document_state

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

## Builder需要实现的部分

- 按官方条款取得 Aya 模型，固定模型文件和数据 revision/hash
- 冻结语言名称映射、文档分组与翻译模板
- 加入逐段质量、语言及结构验收；不使用外部 LLM judge 替代功能检查

## 与相关任务的边界

跨语言保留文档内容的翻译任务，与摘要压缩、问答或代码生成的输出契约不同。

## 数据血缘

- wmt24pp

## 任务范围与条件

- Aya 权重是非商业研究许可且访问需接受条件；无访问权时该任务未准入，不能静默换模型。
- 自动翻译指标不是全部语义质量的保证，参考校准与错误样本需保留。

## 来源记录

- [D_WMT24PP] WMT24++ human reference translations — [来源](https://huggingface.co/datasets/google/wmt24pp)；检查位置：Language-pair configs, source/target/document_id/segment_id/is_bad_source fields
- [D_AYA32] Aya Expanse 32B model card — [来源](https://huggingface.co/CohereLabs/aya-expanse-32b)；检查位置：Supported Languages, How to Use, Model Details, Terms of Use

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
