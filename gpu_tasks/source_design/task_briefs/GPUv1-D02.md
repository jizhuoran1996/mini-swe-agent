# GPUv1-D02 · 把政府报告语料编成可更新的摘要档案

Produce and update a government-report summary archive

**组别**：任务侧模型推理与检索处理　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`longbench_gov_report_summary_archive`

**Workflow family**：`long_document_summarization`

## 任务目标

为给定政府报告集合建立报告 ID 与摘要对应的档案；用本地模型生成可读摘要，交付完整汇总文件，并支持对尚未处理的报告继续追加。

## 具体来源工作负载

LongBench gov_report test 全 200 份报告，Qwen/Qwen2.5-32B-Instruct

## 输入与配置

- LongBench gov_report 原始 test context 与报告标识
- 参考摘要仅提供给验证器
- Qwen2.5-32B-Instruct 和固定摘要结构要求

## 需要完成的工作

- 读取完整报告并按冻结顺序处理，保留原文到结果的哈希映射
- 实际执行长文本 prefill 与较长摘要生成
- 将摘要写入 JSONL/Markdown 档案，原子提交已完成条目以便恢复

## 交付物

- summaries.jsonl
- report_archive.md
- completed_ids.json
- generation_config.json

## 后续使用与状态

在保留模型和已完成清单的 session 中处理 manifest 指定的后续报告，再生成去重后的完整摘要档案。

## 独立验收

- 报告 ID 覆盖与一对一映射检查；禁止摘要为空或复制报告全文冒充摘要
- 重新计算来源 Rouge-L 并用参考运行校准容差
- 随机抽取已输出摘要验证没有跨报告内容或错误输入绑定

## 应拒绝的失败方式

- 所有报告共用一个模板摘要
- 因上下文超限而未声明地丢掉报告尾部
- 只有一份全语料总摘要，没有逐报告交付

## 规模配方

### Debug：仅调通

- **data**：稳定选取 4 份原报告
- **hardware_target**：T2/T3，同一模型和上下文策略
- **purpose**：结构与 oracle 调试

### Reference large：正式生产规模

- **data**：gov_report test 全 200 份原报告
- **model**：Qwen2.5-32B-Instruct，BF16；long-text 配置按模型卡固定
- **hardware_target**：T3：2×80 GiB GPU，模型并行
- **useful_output**：逐报告摘要档案；不以重复生成填充工作量

### 可选扩展：同一任务的变体

- **data**：相同 200 份报告分派至多个独立 worker
- **hardware_target**：T3：2–8 GPU，复制或模型并行的配置需预先冻结
- **not_new_task**：True

## GPU工作与预期资源形态

报告 prefill 与连续文本生成同时覆盖较长输入和较长输出；模型常驻与摘要落盘连接 GPU、主存和工作区。

## 资源标签（待画像验证）

- long_prefill
- long_decode
- weight_residency
- artifact_writes

## 设备能力

- CUDA
- BF16
- multi_gpu_model_parallel

## 后端要求

- 被测 sandbox 能访问声明的 GPU 设备与匹配的 CUDA/driver 用户态库；正式运行不静默转 CPU 或远程模型 API。
- 初始模型和输入在声明的只读路径，产物写入本 session 工作区；驱动兼容性与单/多 GPU 能力准入独立于功能验收。

## 回放约束

- 替换的仅是负责决策的 agent LLM；本任务载入的模型及其 prefill、decode、embedding 或 reranking 每次都真实执行，不返回旧预测冒充执行。
- 冻结模型/数据内容哈希、tokenizer/processor、dtype、算子后端、解码及分片参数；服务端口和作业 ID 在本轮绑定，不能复用旧句柄。
- 工具完成以 CUDA 工作与输出提交完成为准；记录的模型等待不替代服务 ready、CUDA event 或文件落盘依赖。

## Builder需要实现的部分

- 明确完整报告的上下文长度校验；超限处理必须在建包时固定且重新画像
- 封存摘要提示与产物 schema，加入质量校准和原子追加逻辑

## 与相关任务的边界

交付全文摘要，与 D01 的问题定向阅读不同；与 A 组可能共享 GovReport 来源，但此任务不训练参数。

## 数据血缘

- gov_report_longbench

## 任务范围与条件

- 摘要质量为软指标，不能要求逐字复现参考译文式输出。
- 来源语料与训练类任务共享时，family/lineage 应记录，不能当成完全独立数据来源。

## 来源记录

- [D_LONGBENCH_TASKS] LongBench task definitions — [来源](https://github.com/THUDM/LongBench/blob/main/LongBench/task.md)；检查位置：LongBench/task.md: statistics, task description, task construction; qasper, gov_report, repobench-p
- [D_LONGBENCH_EVAL] LongBench evaluation implementation — [来源](https://github.com/THUDM/LongBench/blob/main/LongBench/eval.py)；检查位置：dataset2metric: qasper qa_f1_score, gov_report rouge_score, repobench-p code_sim_score
- [D_QWEN32] Qwen2.5-32B-Instruct model card — [来源](https://huggingface.co/Qwen/Qwen2.5-32B-Instruct)；检查位置：Model details, Quickstart, Processing Long Texts

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
