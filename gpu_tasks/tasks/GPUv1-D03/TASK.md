# GPUv1-D03：交付完整代码补全目录与可调用接口

input/requests.jsonl 为 HumanEval 的 8 个原始 Python function prefix，只给 id/prompt，不给 solution/tests。用 CUDA /models/Qwen--Qwen2.5-Coder-0.5B-Instruct，为每个问题生成可与原始 prefix 组合的 function-body completion。greedy、最多 256 新 tokens、固定 prompt 模板并记录。不得求解 agent 自己写答案代替任务模型生成；可统一去除模型输出的 Markdown 包裹，但必须保存 raw output 和对应 token IDs。
入口 python solution/main.py run --input input --output output；交付 completions.jsonl（id/prompt/raw_generation/token_ids/completion/normalization规则）、run.json；另实现 python solution/main.py serve --port PORT，GET /health 和 POST /complete {id,prompt}。独立检查所有 IDs、fresh greedy model generation、后续新请求、隔离的代码语法与隐藏 unit tests；pass@1 单独报告，debug 不要求 tiny model 全部问题通过。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
