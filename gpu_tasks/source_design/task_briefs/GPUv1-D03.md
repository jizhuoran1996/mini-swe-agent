# GPUv1-D03 · 为代码库上下文建立可调用的跨文件补全工具

Build a callable cross-file code completion tool

**组别**：任务侧模型推理与检索处理　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`longbench_repobench_p_completion_archive`

**Workflow family**：`repository_code_completion`

## 任务目标

为给定 Python/Java 代码库上下文提供下一行补全，产出逐条补全档案和一个接收上下文的本地接口，使后续请求能继续使用已部署模型。

## 具体来源工作负载

LongBench repobench-p test 全 500 条，Qwen/Qwen2.5-Coder-32B-Instruct

## 输入与配置

- LongBench repobench-p test 的跨文件上下文、代码前缀和稳定 ID
- Qwen2.5-Coder-32B-Instruct
- 独立封存的下一行标注

## 需要完成的工作

- 实现输入模板，保持跨文件内容和代码前缀顺序
- 部署 GPU 补全端点，执行全部真实补全并截取约定的下一行结果
- 保留完整原始响应供错误诊断，交付规范化结果
- 交付实际可启动的 repository_completion_service 服务；实现 POST /v1/completions 的请求/响应 schema，并输出本轮逻辑服务绑定。

## 交付物

- completions.jsonl
- raw_generations.jsonl
- completion_service_config.json
- service/serve.py 与 service/launcher.json（可启动的模型服务入口）
- service/request_schema.json、response_schema.json 与 model_config.json
- service/service_binding.json（逻辑服务到本轮 endpoint/模型进程/设备的绑定）
- requests/initial.jsonl、requests/continuation.jsonl 与在线响应/完成事件记录

## 后续使用与状态

对封存的后续上下文分片继续补全，保持原有记录不被覆盖，并检查更新后接口仍可调用。；具体后续请求来自 requests/continuation.jsonl，在 recorded wait 后通过本轮逻辑服务绑定真实提交并验收。

## 独立验收

- 逐 ID 检查输入哈希、结果覆盖和首个有效补全行
- 独立计算 LongBench code_sim_score，并与固定参考运行对齐
- 记录语法异常，但不把来源未提供的整项目测试伪称为原生 oracle
- recorded wait 后，通过逻辑 completion service 向仍存活的本轮模型进程发送冻结留出上下文，验证真实生成的首行补全、模型哈希、请求/结果对应和 CUDA 工作关联；不能以 ready、进程存活或旧 completions.jsonl 代替。

## 应拒绝的失败方式

- 直接复制 reference continuation
- 只返回代码说明而不提供约定的补全内容
- 移除跨文件输入以降低 prefill 工作量
- 离线文件通过但线上模型服务不可用，或在线请求只查旧答案缓存却没有本轮模型工作

## 规模配方

### Debug：仅调通

- **data**：16 条不同代码上下文
- **hardware_target**：T2：单 80 GiB GPU；完整推理路径

### Reference large：正式生产规模

- **data**：repobench-p test 全 500 条
- **model**：Qwen2.5-Coder-32B-Instruct，BF16；模板和结束规则冻结
- **hardware_target**：T2：单 80 GiB GPU 为构建目标；建包时用最长输入验证容量，必要的 T3 profile 单独冻结
- **useful_output**：可重新查询的补全工具及逐条结果

### 可选扩展：同一任务的变体

- **data**：同一语料分片并发服务，不增加重复代码实例
- **hardware_target**：T3：2–4 GPU 模型副本或张量并行
- **not_new_task**：True

## GPU工作与预期资源形态

32B 代码模型对跨文件上下文实际计算；短生成与较长 prefill 的比例区别于报告摘要。

## 资源标签（待画像验证）

- prefill_dominant
- short_decode
- persistent_service

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

- 制作 Repobench 输入转换与首行提取器
- 固定代码模板、推理版本并完成最长上下文容量准入
- 实现 launcher、健康与 /v1/completions 推理协议；把冻结留出请求在记录等待后经本轮 binding 发给实际模型进程，并关联响应与设备事件。

## 与相关任务的边界

代码补全应用，而非训练代码模型、从头编译工程或一般文本问答。

## 数据血缘

- repobench_p_longbench

## 任务范围与条件

- LongBench 片段不是可构建的完整 Git 工作区；不声称有全工程编译或测试覆盖。

## 来源记录

- [D_LONGBENCH_TASKS] LongBench task definitions — [来源](https://github.com/THUDM/LongBench/blob/main/LongBench/task.md)；检查位置：LongBench/task.md: statistics, task description, task construction; qasper, gov_report, repobench-p
- [D_LONGBENCH_EVAL] LongBench evaluation implementation — [来源](https://github.com/THUDM/LongBench/blob/main/LongBench/eval.py)；检查位置：dataset2metric: qasper qa_f1_score, gov_report rouge_score, repobench-p code_sim_score
- [D_QWENCODER32] Qwen2.5-Coder-32B-Instruct model card — [来源](https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct)；检查位置：Model details, Quickstart, Processing Long Texts

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
