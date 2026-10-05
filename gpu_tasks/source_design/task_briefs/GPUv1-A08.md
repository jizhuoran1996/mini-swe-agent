# GPUv1-A08 · 适配70B长报告摘要模型并交付可复用适配器

Adapt a 70B long-report summarizer and deliver reusable adapters

**组别**：语言、语音与推荐模型训练　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`llama2_70b_govreport_lora`

**Workflow family**：`long_document_model_adaptation`

## 任务目标

将70B基础模型适配到政府长报告摘要，交付与明确基础权重对应的LoRA适配器，并为独立报告生成摘要。训练、保存、后续加载和实际长文解码均在sandbox内执行。

## 具体来源工作负载

MLPerf Llama2-70B LoRA + SCROLLS GovReport; public-asset derivative

## 输入与配置

- meta-llama/Llama-2-70b-hf的已获准固定公开权重版本
- tau/scrolls 的 gov_report 全部公开train，validation用于校验
- MLPerf来源的8192-token、LoRA rank16/alpha32设计；使用公开HF模块命名映射，不依赖会员专属fused bundle

## 需要完成的工作

- 构造固定报告到摘要监督样本，明确长于8192 token的截断/packing与标签掩码规则
- 对q/k/v/o attention投影执行真实LoRA更新；合并投影到分离投影的映射须验证，训练一遍完整train
- 交付adapter和基础模型hash后重新加载，在保留报告上生成摘要并计算ROUGE/长度与覆盖信息

## 交付物

- adapter/、base_model_manifest.json、tokenizer和prompt模板
- heldout_summaries.jsonl：report_id及真实预测
- training_coverage.json、公共资产预处理说明与评测报告

## 后续使用与状态

用同一个基础模型和新adapter处理另一批长报告，生成摘要和报告ID映射；允许同session中保留已加载权重等待后续请求。

## 独立验收

- 确认70B基础模型标识和adapter模块映射，独立重载并实际处理长输入
- 核验全部train覆盖、label mask和adapter真实更新，validation未混入训练
- 重新计算ROUGE及固定样本loss，与参考校准容差比较；不使用MLPerf专有模型的绝对阈值
- 摘要非复制reference或固定模板，逐报告输出完整

## 应拒绝的失败方式

- 交付另一个小模型或空adapter
- 把8192-token声明改成只读报告开头几十个token
- 使用未经本轮训练的现成摘要模型或提交参考摘要

## 规模配方

### Debug：仅调通

- **data**：GovReport固定8条训练报告、2条验证报告
- **work**：同一70B权重的adapter映射、短预算训练和重载验证
- **hardware_target**：T3 4–8×80 GiB；不能把7B调试结果当formal任务

### Reference large：正式生产规模

- **data**：完整GovReport train一遍；固定全部公开validation或其声明的完整报告ID集合
- **model**：Llama2-70B BF16 + LoRA r16，8192-token监督上限
- **output**：可复用adapter及保留长报告摘要
- **hardware_target**：T3 8×80 GiB，FSDP/ZeRO与NCCL；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：同一GovReport集合和任务目标
- **work**：比较批准的张量/参数分片配置与后续驻留；不额外复制报告制造压力
- **hardware_target**：T3 8 GPUs；更大集群另设场景

## GPU工作与预期资源形态

70B真实权重驻留与长序列激活带来明确的高显存和通信需求；LoRA降低可训练状态但不会消除基础模型与长输入计算。

## 资源标签（待画像验证）

- large_model_residency
- long_sequence_training
- adapter_checkpoint
- parameter_sharding
- all_gather
- retained_model

## 设备能力

- CUDA
- BF16
- FlashAttention2
- NCCL
- multi_GPU_parameter_sharding

## 后端要求

- 授权资产提前准备且固定hash，GPU作业共同准入
- 声明互连、分片、CPU offload及checkpoint边界

## 回放约束

- 公共HF版本与MLPerf fused模型不是同一数值实现；采集一次本派生协议并跨后端固定
- 任务端70B训练和摘要推理真实执行，不受agent LLM replay替代
- 应用adapter/checkpoint不表示可以透明快照GPU context

## Builder需要实现的部分

- 取得Llama2权重授权并固定public GovReport数据
- 实现公共HF q/k/v/o LoRA映射、长输入处理和质量参考
- 完成实际70B训练轨迹、容差和资源画像

## 与相关任务的边界

长报告摘要适配有不同监督数据、长文状态和交付adapter；不同于A01通用聊天SFT。与D组GovReport任务的区别是本任务必须训练并交付更新后的模型。

## 数据血缘

- scrolls_gov_report

## 任务范围与条件

- 访问受Meta许可约束；本包不提供权重或会员资产
- 这是公共资产派生任务，不宣称符合正式MLPerf规则或复现其阈值

## 来源记录

- [A_MLPERF_LORA] MLPerf Llama2-70B LoRA benchmark README — [来源](https://github.com/mlcommons/training/blob/master/llama2_70b_lora/README.md)；检查位置：Llama2-70B; SCROLLS GovReport; sequence length 8192; LoRA r16 alpha32; eight A100 80GB devices; official raw README inspected
- [A_SCROLLS] SCROLLS benchmark repository — [来源](https://github.com/tau-nlp/scrolls)；检查位置：GovReport long-document summarization; Hugging Face tau/scrolls dataset and evaluation code
- [A_LLAMA2_MODEL] Meta Llama 2 70B Hugging Face model — [来源](https://huggingface.co/meta-llama/Llama-2-70b-hf)；检查位置：Concrete public model distribution to be acquired under authorized access for A08

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
