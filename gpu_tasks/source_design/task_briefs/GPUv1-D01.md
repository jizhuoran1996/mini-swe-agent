# GPUv1-D01 · 部署科研论文阅读服务并生成逐题答案档案

Deploy a scientific-paper reader and produce question-level answer records

**组别**：任务侧模型推理与检索处理　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`longbench_qasper_full_answer_archive`

**Workflow family**：`document_question_answering`

## 任务目标

把给定论文与问题整理成可重复处理的阅读队列，部署本地 GPU 阅读服务，交付逐题答案、来源文档映射和可继续接受同语料后续问题的服务。

## 具体来源工作负载

LongBench qasper test（完整 200 条），Qwen/Qwen2.5-32B-Instruct；保留原始论文上下文和问题

## 输入与配置

- LongBench qasper test 的 context/input/_id 与独立保存的答案标注
- Qwen/Qwen2.5-32B-Instruct 官方权重、tokenizer 与 chat template
- 固定问题顺序、文档哈希及不读取参考答案的提示模板

## 需要完成的工作

- 校验全部论文与问题 ID，实际加载模型并等待服务就绪
- 用完整来源上下文逐题生成答案，输出 token 与任务 ID 一一对应
- 提交 JSONL 答案和可按文档 ID 查回上下文的阅读档案

## 交付物

- answers.jsonl
- document_manifest.json
- reader_service_config.json
- reference_metric_inputs.json

## 后续使用与状态

在已加载模型上处理预先封存的后续问题分片；继续使用同一论文映射并保留先前答案，报告新增条目。

## 独立验收

- 检查所有问题恰好一条最终结果且输入文档哈希匹配
- 独立运行 LongBench qa_f1_score，并与固定模型参考运行校准的质量容差比较
- 抽查当前服务对留出问题的真实响应；评分不接受自报数值

## 应拒绝的失败方式

- 用保存的参考答案填表但未调用任务侧模型
- 把问题和论文错配、静默遗漏超长上下文
- 仅提交吞吐日志而无逐题结果

## 规模配方

### Debug：仅调通

- **data**：按稳定 ID 取 8 条原始问题
- **model**：同一 32B 模型；小模型调试另标 debug-only
- **hardware_target**：T2：单 80 GiB GPU 起步；仅检查链路

### Reference large：正式生产规模

- **data**：qasper test 全 200 条，不复制扩充
- **model**：Qwen2.5-32B-Instruct，BF16，完整上下文；依据官方 long-text 说明固定上下文配置
- **hardware_target**：T3：2×80 GiB GPU，模型并行；这是构建目标而非实测最低配置
- **useful_output**：完整答案档案与可重访服务

### 可选扩展：同一任务的变体

- **data**：同一全量问题按独立队列分片，不增加虚构问题
- **hardware_target**：T3：最多 4 GPU；分片复制与模型并行方案分别冻结
- **not_new_task**：True

## GPU工作与预期资源形态

32B 常驻权重、论文 prefill 和答案 decode 产生真实计算；等待期间模型驻留，后续问题重新访问其设备状态。

## 资源标签（待画像验证）

- weight_residency
- context_prefill
- autoregressive_decode
- state_retained_between_calls

## 设备能力

- CUDA
- BF16
- multi_gpu_model_parallel

## 后端要求

- 被测 sandbox 能访问声明的 GPU 设备与匹配的 CUDA/driver 用户态库；正式运行不静默转 CPU 或远程模型 API。
- 初始模型和输入在声明的只读路径，产物写入本 session 工作区；驱动兼容性与单/多 GPU 能力准入独立于功能验收。
- 多 GPU 运行须固定设备拓扑与 tensor/model parallel 实现，允许所需进程通信。

## 回放约束

- 替换的仅是负责决策的 agent LLM；本任务载入的模型及其 prefill、decode、embedding 或 reranking 每次都真实执行，不返回旧预测冒充执行。
- 冻结模型/数据内容哈希、tokenizer/processor、dtype、算子后端、解码及分片参数；服务端口和作业 ID 在本轮绑定，不能复用旧句柄。
- 工具完成以 CUDA 工作与输出提交完成为准；记录的模型等待不替代服务 ready、CUDA event 或文件落盘依赖。
- KV cache 是否跨问题复用和服务等待时是否保留模型要写入场景；不能假定每次回复都保留全部 KV。

## Builder需要实现的部分

- 固定 LongBench 数据与模型 revision/hash，制作输入/答案隔离的数据包
- 实现服务 ready/完成事件、每题 JSONL 提交和答案 oracle
- 参考运行后确定上下文与质量配置并采集完整 session

## 与相关任务的边界

科研论文证据问答；与 D02 的整篇摘要、D03 的代码补全在交付语义上不同。

## 数据血缘

- qasper_longbench

## 任务范围与条件

- 原问题数量有限，不能据此声称大量独立的科研 agent 任务；这是一个批处理工作流候选。
- LongBench 标注可能不覆盖所有语义等价答案，质量阈值需参考校准。

## 来源记录

- [D_LONGBENCH_TASKS] LongBench task definitions — [来源](https://github.com/THUDM/LongBench/blob/main/LongBench/task.md)；检查位置：LongBench/task.md: statistics, task description, task construction; qasper, gov_report, repobench-p
- [D_LONGBENCH_EVAL] LongBench evaluation implementation — [来源](https://github.com/THUDM/LongBench/blob/main/LongBench/eval.py)；检查位置：dataset2metric: qasper qa_f1_score, gov_report rouge_score, repobench-p code_sim_score
- [D_QWEN32] Qwen2.5-32B-Instruct model card — [来源](https://huggingface.co/Qwen/Qwen2.5-32B-Instruct)；检查位置：Model details, Quickstart, Processing Long Texts

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
