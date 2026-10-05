# GPUv1-D10：生成完整翻译目录与可复用翻译入口

用CUDA /models/Qwen--Qwen2.5-0.5B-Instruct chat template翻译input/requests.jsonl的8条真实WMT14英语句为德语，greedy最多128新tokens，不提供目标句。入口 python solution/main.py run --input input --output output；输出 translations.jsonl（id/translation/raw_text/token_ids）、run.json；另支持 translate --text TEXT --source-language English --target-language German --output JSON 新句子。独立检查全coverage、token生成重算、新句子、CUDA调用，BLEU/chrF单独报告；不得调用预存译文。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
