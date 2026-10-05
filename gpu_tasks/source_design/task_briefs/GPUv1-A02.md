# GPUv1-A02 · 训练并验证偏好对齐后的对话模型

Produce and validate a preference-aligned chat model

**组别**：语言、语音与推荐模型训练　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`zephyr7b_ultrafeedback_dpo`

**Workflow family**：`language_preference_alignment`

## 任务目标

给定已训练的 SFT 模型和偏好样本，交付能够正确加载的偏好对齐模型，并提供独立候选回复对上的评分审计及实际对话回复。

## 具体来源工作负载

Alignment Handbook Zephyr DPO + corrected HuggingFaceH4/ultrafeedback_binarized train_prefs

## 输入与配置

- alignment-handbook/zephyr-7b-sft-full 的固定可获取版本；独立初始资产，不要求先运行 A01
- 修正标签后的 UltraFeedback train_prefs 全部 61,135 对；test_prefs 2,000 对
- 上游 DPO full 配置：beta=0.01、max_length=1024、max_prompt_length=512、一轮；独立训练/测试切分

## 需要完成的工作

- 核对 chosen/rejected 角色、相同 prompt 和模板，排除格式损坏记录并保留清单
- 进行真实 DPO 更新，保持参考策略固定，保存参数、参考模型标识及优化器进度
- 用新模型对保留 pairs 计算相对偏好分数，并为指定 prompts 生成真实回复

## 交付物

- aligned_model/ 和 tokenizer/template
- pair_scores.parquet：prompt_id、chosen/rejected 的可复算 log probabilities
- validation_report.json 与训练覆盖清单

## 后续使用与状态

接收一组未用于训练的候选回复对，利用当前模型和冻结参考策略执行排序审计，输出可追溯分数及异常样本。

## 独立验收

- 重载交付权重并计算保留样本的策略/参考 log probabilities
- 检查 chosen/rejected 映射、prompt 去重和 held-out 隔离
- 偏好准确率、NLL 和更新后质量在参考校准容差内；不要求每一对均变好
- 检查实际参数更新与有效进度，GPU 占用不能代替功能验收

## 应拒绝的失败方式

- 交换 chosen/rejected 却只报告漂亮分数
- 复制输入 SFT 模型或预存 pair scores
- 用远程奖励 API 代替本地 DPO 或把参考策略也训练了

## 规模配方

### Debug：仅调通

- **data**：固定 256 对训练、32 对测试
- **work**：同样的策略与参考模型，检查 loss 和重载
- **hardware_target**：T3 2–4×80 GiB，微批调整只用于 debug

### Reference large：正式生产规模

- **data**：完整 61,135 对训练，独立 2,000 对测试
- **model**：7B policy 全参数 DPO + 冻结参考策略，1 epoch
- **output**：对齐模型、候选回复审计与真实解码
- **hardware_target**：T3 4–8×80 GiB，NCCL；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：同一 preference split
- **work**：冻结等效训练目标后扫描并行布局或参考 log-prob 预计算策略；作为配置差异记录
- **hardware_target**：T3 8 GPUs；不新增任务数

## GPU工作与预期资源形态

偏好成对序列、训练策略及参考策略共同形成与普通 SFT 不同的计算和驻留状态。

## 资源标签（待画像验证）

- pairwise_training
- reference_model_residency
- optimizer_state
- activation_memory
- checkpoint_io

## 设备能力

- CUDA
- BF16
- NCCL

## 后端要求

- 固定训练和参考策略的数值实现
- 足够存放初始化、输出权重和优化器状态的工作空间

## 回放约束

- DPO 前向/反向与任务端解码真实执行；不调用 agent 的在线决策模型
- 如果采集采用预计算 reference scores，输入 hash 与预计算成本边界必须冻结

## Builder需要实现的部分

- 验证初始 SFT 权重获取并锁定 revision
- 建立 pair 级验证器和可复算 log-prob 输出
- 参考运行后确定数值容差及完整训练资源画像

## 与相关任务的边界

输出偏好对齐策略与候选排序审计，监督目标是相对偏好；与 A01 的教师回复模仿、A08 的长文摘要具有不同任务语义。

## 数据血缘

- ultrafeedback_binarized

## 任务范围与条件

- 沿用公开偏好数据，其标签质量不等于真实用户整体偏好
- 采用修正数据和独立 test_prefs，不直接宣称复现原 Zephyr leaderboard 结果

## 来源记录

- [A_ALIGNMENT_DPO] Alignment Handbook: Zephyr 7B DPO full recipe — [来源](https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/dpo/config_full.yaml)；检查位置：SFT model initialization; UltraFeedback chosen/rejected; beta 0.01; length 1024; one epoch
- [A_ULTRAFEEDBACK] UltraFeedback binarized dataset card — [来源](https://huggingface.co/datasets/HuggingFaceH4/ultrafeedback_binarized)；检查位置：train_prefs 61,135 pairs; test_prefs 2,000; corrected labels and contamination note
- [A_ZEPHYR_SFT_MODEL] Alignment Handbook Zephyr 7B SFT full model — [来源](https://huggingface.co/alignment-handbook/zephyr-7b-sft-full)；检查位置：Public SFT initialization for A02; model card reports 7B BF16 and eight-device training

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
