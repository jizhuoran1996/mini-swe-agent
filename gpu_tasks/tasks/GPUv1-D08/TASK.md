# GPUv1-D08：生产可复用的多语言文档向量与常驻编码接口

input/documents.jsonl 是 MIRACL 的真实 Arabic/Hindi 各 100 个段落，字段 id/lang/title/text。模型 /models/sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2。使用原模型 tokenizer 与 Transformer encoder，attention-mask mean pool + L2 normalize，max_length=128；模型实际 CUDA 推理。不需要 sentence-transformers 包，可薄封装 Transformers。
入口 python solution/main.py encode --input input/documents.jsonl --output output；输出 embeddings.npy (200,384) float32、document_ids.json（原顺序）、run.json（source/model hash、参数/覆盖/同步耗时）。另实现 python solution/main.py serve --port PORT，GET /health 在真实 CUDA ready 后返回 model/device，POST /encode {texts:[...]} 返回 normalized embeddings。独立标准 tokenizer/encoder/mean-pooling 重算全部向量，cosine >= .9999、fresh process 后不依赖离线结果的新文本、两轮间 idle 继续可调用、SIGTERM 释放进程。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
