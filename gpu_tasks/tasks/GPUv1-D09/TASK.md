# GPUv1-D09：交付可继续使用的候选文档重排器

input/requests.jsonl 有 8 个真实 MS MARCO query/candidate-list，不提供 relevance。模型 /models/cross-encoder--ms-marco-MiniLM-L6-v2；用 AutoModelForSequenceClassification 实际 CUDA cross-encode query/passage pair，max_length=256，score=raw logit，稳定按 score 降序、同分 passage id 升序。
入口 python solution/main.py run --input input --output output；输出 rankings.jsonl（query id、全部 passage id/raw_score、rank），run.json；另实现 python solution/main.py serve --port PORT，GET /health 和 POST /rerank {query,passages:[{id,text}]}。独立标准模型重算 logits <=1e-4、全候选无漏项无重复、排名正确、fresh service 新候选/idle 后复用、SIGTERM 清理；真实标签 MRR 另行报告。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
