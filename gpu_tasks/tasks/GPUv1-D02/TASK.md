# GPUv1-D02：交付完整政府报告摘要目录与后续接口

input/requests.jsonl 有 16 个真实 GovReport test 报告，仅 id/document，不提供参考摘要。使用 CUDA /models/Qwen--Qwen2.5-0.5B-Instruct，报告最多 2048 tokens，greedy decode 至多 128 新 tokens。创建每个报告的可读摘要，保留对应 ID 和 truncation。禁止直接摘取前缀代替模型生成或用任何参考摘要。
入口 python solution/main.py run --input input --output output；python solution/main.py infer --input input/requests.jsonl --output output/reloaded.jsonl。输出 summaries.jsonl（id/summary/token_ids/input_token_count/truncated）、run.json（actual model revision、parameters、GPU阶段耗时/coverage）。支持 --serve 作为可继续查询的 HTTP 服务（/health 与 POST /infer {id,document}），ready 必须在真实 CUDA model load 后；后续新报告用同一模型处理。独立检查全覆盖、正确重载、greedy token 重算、new request、idle 后继续响应、SIGTERM 清理；ROUGE/summary correctness 独立报告，不把 debug 当正式质量通过。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
