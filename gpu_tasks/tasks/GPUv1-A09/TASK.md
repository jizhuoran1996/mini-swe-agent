# GPUv1-A09：交付可重载的问答双编码检索模型

用真实 SQuAD train question/context 对训练 CUDA 双编码器，基础模型 /models/prajjwal1--bert-tiny，question 与 passage encoder 可共享或独立。最大 128 tokens，attention-mask mean pooling + L2 normalize，in-batch contrastive cross entropy；同一个 context 对应多道 question 时必须用 multi-positive mask 或去重批次，不能把相同 context 当负例。至少一次完整训练样本 pass，固定 seed。
入口 python solution/main.py train --input input --output output；python solution/main.py encode --checkpoint output/checkpoint --input input/validation.jsonl --output output/reloaded。输出 checkpoint/（HF encoder 或标准 state/config）、training_state.pt、question_embeddings.npy、passage_embeddings.npy（validation 顺序）、retrieval.json（cosine top-k 与对应 IDs）、run.json。独立检查更新、归一化、全部覆盖、CUDA backward、fresh-process 双编码一致。报告 validation Recall@1/5；同 passage 的多个 IDs 必须采用内容组判断。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
