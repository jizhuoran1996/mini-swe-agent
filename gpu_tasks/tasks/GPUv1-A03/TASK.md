# GPUv1-A03：适配并交付可离线英德翻译模型

对真实 WMT14 英德 parallel sentences 微调 Marian 模型 /models/Helsinki-NLP--opus-mt-en-de。input/train.jsonl 有 64 个 en/de 对，validation.jsonl 有 8 个官方 test 对。CUDA seq2seq teacher forcing，目标 padding label=-100，max_length=128，全部训练句至少一次优化器更新，固定 seed。翻译验证句仅以 en 为输入，禁止将验证 de 拼进生成 prompt。
入口 python solution/main.py train --input input --output output；python solution/main.py translate --checkpoint output/checkpoint --input input/validation.jsonl --output output/translations.jsonl。交付标准 HF checkpoint（tokenizer/config/weights）、training_state.pt（optimizer/step/RNG）、translations.jsonl（id/en/translation/token_ids）、run.json（before/after loss 和 source hash/真实参数/同步耗时）。独立检查参数更新、teacher forcing NLL、完整 coverage、新进程重载产生相同 token、空输出失败。质量统计独立 chrF/BLEU，但 debug 仅验真模型执行及可复用交付，不宣称达到正式翻译 benchmark 质量。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
