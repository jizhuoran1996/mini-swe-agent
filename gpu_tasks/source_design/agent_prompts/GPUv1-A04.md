# GPUv1-A04 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

将指定 Whisper 模型适配到完整有声读物转写数据，交付可重新加载的模型，并完成 clean/other 测试集的逐条转录及错误分析。

### 来源和工作范围

SpeechBrain Whisper-large-v3 decoder fine-tuning on LibriSpeech960

### 交付要求

- asr_model/：训练后的 decoder、对应 encoder 引用、processor 和配置
- transcripts.jsonl：utterance_id、预测与音频标识
- wer_report.json 与实际训练样本清单

### 必须完成的工作

- 验证16kHz音频和 transcript ID，固定 normalization、采样和分段方式
- 按来源方案冻结 encoder，真实训练 decoder 一轮并保存完整可加载状态
- 用新模型转录官方测试集，分别计算 clean/other WER 和 CER

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

继续处理保留的 dev-other 音频并输出错误类别报告，复用已训练模型和处理器，测试跨调用的大模型重新使用。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
