# GPUv1-D01：交付长论文问答目录与后续查询

对8个真实 LongBench Qasper 文档/问题执行 CUDA Qwen2.5-0.5B-Instruct 问答，document 最多2048 tokens，保留question并用chat template，greedy最多128新tokens。入口 python solution/main.py run --input input --output output；输出 answers.jsonl（id/answer/raw_text/token_ids/input_tokens/truncated）、run.json。另支持 serve --port PORT，/health 和 POST /infer {id,document,question}，模型必须加载到CUDA后ready，后续问题不能依赖原输出。独立检查coverage、模型重算、fresh request/idle/SIGTERM，答案准确率另报。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
