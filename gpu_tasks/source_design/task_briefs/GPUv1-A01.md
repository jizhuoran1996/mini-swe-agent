# GPUv1-A01 · 训练可交付的多轮指令对话模型

Train and package an instruction-following chat model

**组别**：语言、语音与推荐模型训练　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`mistral7b_ultrachat_instruction_sft`

**Workflow family**：`language_supervised_adaptation`

## 任务目标

用指定多轮对话数据训练一个可离线加载的指令模型，交付模型权重、分词器、聊天模板和训练清单，并在独立验证对话上给出真实预测。交付应能被另一个进程直接使用。

## 具体来源工作负载

Alignment Handbook Zephyr SFT: mistralai/Mistral-7B-v0.1 + HuggingFaceH4/ultrachat_200k train_sft

## 输入与配置

- mistralai/Mistral-7B-v0.1 的获准固定权重版本及 tokenizer
- UltraChat200k 的完整 train_sft；test_sft 仅用于验证
- Zephyr SFT full 配置，2048 token 上限，一轮训练；禁用 push_to_hub 和在线日志上报

## 需要完成的工作

- 固定聊天模板、终止符和截断策略，保存每个训练记录的标识；训练/验证不合并
- 执行真实前向、反向与参数更新，保存模型、优化器及数据进度
- 重新加载产物，对指定的验证对话产生完整回复和 token 级 NLL

## 交付物

- model/：训练后的权重、tokenizer、chat_template
- training_manifest.json：输入版本、样本覆盖、配置和实际训练进度
- validation_predictions.jsonl 与可复算的 token loss 汇总

## 后续使用与状态

后续请求用已保存模型处理另一批冻结的多轮验证会话；模型可在同一 session 内继续驻留或重新加载，行为由采集到的轨迹决定。

## 独立验收

- 独立进程实际加载模型及模板，检查词表、权重结构与有限数值
- 核对本轮训练样本覆盖和参数更新证据；验证集不得进入训练清单
- 对保留对话重新计算 NLL 和确定性解码结果；与参考执行校准的容差比较，不以自报 loss 通过
- 质量门槛和 GPU 资源画像分别准入

## 应拒绝的失败方式

- 只复制原始 Mistral 权重而未训练
- 训练中使用 test_sft 或提交预写回复
- 只写日志或返回远程推理结果，未产生本轮可加载模型

## 规模配方

### Debug：仅调通

- **data**：train_sft 固定 256 个互异会话，test_sft 固定 32 个
- **work**：同一 7B 架构和训练接口的小规模连通性检查
- **hardware_target**：T3 2–4×80 GiB，或通过已声明的参数高效 debug 配置检查加载；debug 结果不与 formal 配置混用

### Reference large：正式生产规模

- **data**：完整 train_sft，完整 test_sft 保留；最长序列 2048
- **model**：Mistral-7B-v0.1 全参数 SFT，一轮训练
- **output**：可加载的指令模型及验证预测
- **hardware_target**：T3 8×80 GiB，单节点 NCCL；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：同一数据和目标
- **work**：比较不同并行布局或设备数；仍为同一任务实例，重新冻结训练预算与数值协议
- **hardware_target**：T3 4–8 GPUs；设备改变不新增 task ID

## GPU工作与预期资源形态

7B 模型反向传播需要持续张量计算、激活和优化器状态；导出和再次加载形成有用途的大模型状态流转。

## 资源标签（待画像验证）

- dense_training
- optimizer_state
- activation_memory
- checkpoint_io
- retained_model
- all_reduce

## 设备能力

- CUDA
- BF16
- NCCL
- FlashAttention2-compatible kernels

## 后端要求

- 暴露实际 GPU 和匹配驱动，固定 PyTorch/DeepSpeed/FlashAttention 版本
- 多 GPU rank 间通信、共享内存和可写 checkpoint 目录

## 回放约束

- 被训练的语言模型属于工具工作，其训练和后续预测均真实执行；只有 agent 决策模型的 API 被替换
- checkpoint 写完且分布式 barrier 完成后才进入后续步骤；端口和 rank rendezvous 以运行绑定处理

## Builder需要实现的部分

- 固定源码、权重和数据哈希，制作离线初始环境
- 将上游混合切分调整为本任务声明的独立 train/test
- 实现模型重载验收、采集训练轨迹并测量 GPU/宿主成本

## 与相关任务的边界

学习多轮指令响应；A02学习候选回复偏好，A08学习长报告压缩。任务目标和监督数据不同，非同一任务的 batch 或模型大小变体。

## 数据血缘

- ultrachat_200k

## 任务范围与条件

- 完整全参数训练适合有多 GPU 预算的扩展；不以本配置声称复现官方 Zephyr 分数
- 模型最终质量和训练耗时仍需参考运行确定

## 来源记录

- [A_ALIGNMENT_SFT] Alignment Handbook: Zephyr 7B SFT full recipe — [来源](https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/sft/config_full.yaml)；检查位置：Mistral-7B-v0.1; UltraChat train_sft; max_seq_length 2048; one epoch
- [A_ULTRACHAT] UltraChat 200k dataset card — [来源](https://huggingface.co/datasets/HuggingFaceH4/ultrachat_200k)；检查位置：train_sft/test_sft conversation splits and messages schema
- [A_MISTRAL_MODEL] Mistral 7B v0.1 official model card — [来源](https://huggingface.co/mistralai/Mistral-7B-v0.1)；检查位置：7B base model and tokenizer used by A01

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
