# GPUv1-A08：训练并交付长报告摘要 LoRA adapter

用 GovReport 真实报告/摘要微调 /models/Qwen--Qwen2.5-0.5B-Instruct。train.jsonl 为 32 个 document/summary 对，validation.jsonl 为 4 个不同官方 test 报告。报告仅前 384 tokens，目标 summary 最多 128 tokens。CUDA LoRA，rank=8，目标 q_proj/v_proj，仅 assistant summary 的 token 计入 loss，prompt/padding label=-100，每个报告至少使用一次、固定 seed。冻结基础模型。
入口 python solution/main.py train --input input --output output；python solution/main.py summarize --adapter output/adapter --input input/validation.jsonl --output output/summaries.jsonl。交付标准 PEFT adapter/，training_state.pt（optimizer、step、RNG、基础 model/revision 引用）、summaries.jsonl（id/text/token_ids）、run.json。独立要求 adapter 非零且基础权重未改、完整覆盖、valid finite loss、fresh process 加载基础+adapter 生成相同 tokens；验证 summary 不可加入生成 prompt。小上下文/模型输出质量单独报告。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
