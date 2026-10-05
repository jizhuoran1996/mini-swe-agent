# GPUv1-A04 · 适配大规模语音转写模型并交付转录结果

Adapt a large ASR model and deliver transcriptions

**组别**：语言、语音与推荐模型训练　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`whisper_large_v3_librispeech960_decoder_tuning`

**Workflow family**：`supervised_speech_recognition`

## 任务目标

将指定 Whisper 模型适配到完整有声读物转写数据，交付可重新加载的模型，并完成 clean/other 测试集的逐条转录及错误分析。

## 具体来源工作负载

SpeechBrain Whisper-large-v3 decoder fine-tuning on LibriSpeech960

## 输入与配置

- openai/whisper-large-v3 固定权重和处理器版本
- LibriSpeech train-clean-100+train-clean-360+train-other-500；dev-clean/test-clean/test-other
- SpeechBrain train_with_whisper.py；train_hf_whisper.yaml 明确覆盖 whisper_hub=large-v3

## 需要完成的工作

- 验证16kHz音频和 transcript ID，固定 normalization、采样和分段方式
- 按来源方案冻结 encoder，真实训练 decoder 一轮并保存完整可加载状态
- 用新模型转录官方测试集，分别计算 clean/other WER 和 CER

## 交付物

- asr_model/：训练后的 decoder、对应 encoder 引用、processor 和配置
- transcripts.jsonl：utterance_id、预测与音频标识
- wer_report.json 与实际训练样本清单

## 后续使用与状态

继续处理保留的 dev-other 音频并输出错误类别报告，复用已训练模型和处理器，测试跨调用的大模型重新使用。

## 独立验收

- 加载本轮模型进行真实音频解码；核对全部 utterance IDs
- 独立重算 WER/CER，容差来自同一转写和归一化协议的参考执行
- 检查训练 decoder 与初始化不同而 frozen encoder 一致
- 校验音频非静音填充、未重复短音频作为全量输入

## 应拒绝的失败方式

- 复制参考 transcript 或返回原始模型的预存结果
- 把源码默认 medium.en 当作大模型配置
- 只提取音频特征而未执行指定 decoder 更新

## 规模配方

### Debug：仅调通

- **data**：train-clean-100 内固定50条，test-clean固定20条
- **work**：同一 large-v3 模型的输入、训练和输出检查
- **hardware_target**：T1 1×48 GiB 或 T2 1×80 GiB

### Reference large：正式生产规模

- **data**：完整960小时官方训练分割，一轮；完整test-clean/test-other
- **model**：Whisper-large-v3，冻结 encoder、训练 decoder
- **output**：适配模型和完整测试转录
- **hardware_target**：T2 1×80 GiB，或 T3 2×40–80 GiB；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：同一完整960小时集合
- **work**：数据并行与数据加载布局改变作为配置，不新增任务
- **hardware_target**：T3 4 GPUs，NCCL

## GPU工作与预期资源形态

大语音模型的 decoder 反向传播、长时音频特征计算和后续 beam search 都是真实 GPU 工作；音频加载与计算可交叠。

## 资源标签（待画像验证）

- audio_decode_input
- encoder_decoder_training
- retained_model
- host_device_transfer
- checkpoint_io

## 设备能力

- CUDA
- FP16 or declared BF16
- NCCL when multi-GPU

## 后端要求

- 可读取完整音频库并固定 soundfile/ffmpeg 等依赖
- 持久 checkpoint 路径和实际 GPU 内存计量

## 回放约束

- 模型等待不替代 GPU 音频编码或训练；任务端 ASR 推理仍执行
- 异步数据加载器和训练进程按实际状态保留

## Builder需要实现的部分

- 落实large-v3 override并锁定权重/数据hash
- 确定大模型参考 batch/梯度积累与完整转录容差
- 采集功能正确的完整训练—评测轨迹

## 与相关任务的边界

监督目标为原语言逐字转录；A05跨语言翻译，A06不依赖文本标签而输出语音表示。

## 数据血缘

- librispeech

## 任务范围与条件

- 只覆盖一种冻结encoder的适配方法；全参数更新应作为同任务配置
- 实际训练时长和峰值显存尚未测量

## 来源记录

- [A_WHISPER_RECIPE] SpeechBrain LibriSpeech transformer and Whisper recipes — [来源](https://github.com/speechbrain/speechbrain/blob/develop/recipes/LibriSpeech/ASR/transformer/README.md)；检查位置：Whisper large-v3 decoder fine-tuning for one epoch; train_with_whisper.py and train_hf_whisper.yaml
- [A_LIBRISPEECH] LibriSpeech ASR corpus, SLR12 — [来源](https://www.openslr.org/12)；检查位置：train-clean-100, train-clean-360, train-other-500 and official dev/test archives

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
