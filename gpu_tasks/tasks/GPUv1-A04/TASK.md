# GPUv1-A04：适配真实语音转写模型并交付完整转录

input/train.jsonl 有 16 个真实 LibriSpeech 16kHz WAV 与官方英文转录，validation.jsonl 有 8 个独立录音，没有提供转录标签；audio 路径相对于 input/。用 /models/openai--whisper-tiny 实际 CUDA teacher-forced seq2seq 微调，Whisper 标准 80-bin 特征，音频最长30秒（本输入都小于30秒），目标仅来自训练转录，padding=-100，每条录音至少进入一次优化器更新、固定 seed。
入口 python solution/main.py train --input input --output output；python solution/main.py transcribe --checkpoint output/checkpoint --input input/validation.jsonl --output output/transcripts.jsonl。后者 audio 相对路径默认从输入清单父目录解析。交付标准 HF model+processor checkpoint/、training_state.pt（optimizer/step/RNG）、transcripts.jsonl（id/text/token_ids/duration）、run.json（参数/loss/每录音覆盖与截断/同步耗时）。独立检查更新、CUDA encoder/decoder/backward、标准重载新录音、所有验证录音处理和 WER（debug 单独报告），禁止输出训练文本查表或把任务模型换成 solving LLM。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
