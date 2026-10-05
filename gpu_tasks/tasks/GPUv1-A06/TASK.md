# GPUv1-A06：在无标注录音上扩展可复用语音表示

input/train.jsonl 的16段真实16kHz语音没有文本标签；validation.jsonl 是8个不同录音。基础模型 /models/facebook--wav2vec2-base。用 Wav2Vec2ForPreTraining 在 CUDA 上执行 masked latent contrastive pretraining（含 codevector diversity loss；不能用纯 waveform MSE 或 ASR 标签代替）。每段最多取开头4秒，mask span、negative samples 按官方 Wav2Vec2 方法生成，记录配置与固定seed，所有录音至少一次有效 optimizer update。
入口 python solution/main.py train --input input --output output；python solution/main.py encode --checkpoint output/checkpoint --input input/validation.jsonl --output output/reloaded。交付标准 HF checkpoint/、training_state.pt（optimizer/step/RNG）、features.npy（8条录音 attention-mask mean pooled、768维且L2 normalized）、run.json（contrastive/diversity loss、mask/negative数、源和截断/同步计时）。独立要求梯度/权重真实改变、loss finite、mask不选padding、CUDA forward/backward、fresh checkpoint相同录音可重算特征。禁止生成随机音频或从目标文本伪造特征。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
