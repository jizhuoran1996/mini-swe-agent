# GPUv1-A10：适配可复用的百科文本编码器

对 WikiText-2 真实百科段落执行 CUDA masked-language-model training。输入 train.jsonl/validation.jsonl 是真实文本，模型 /models/prajjwal1--bert-tiny。使用标准 BERT MLM head；每次训练 mask_rate=0.15，排除特殊 token 和 padding，80% mask/10% random/10% unchanged，未选 token 的 label=-100。至少一次完整训练集 pass，max_tokens=128、固定 seed。
入口 python solution/main.py train --input input --output output；python solution/main.py embed --checkpoint output/checkpoint --input input/validation.jsonl --output output/embeddings.npy。交付标准 HF checkpoint/、training_state.pt（optimizer/step/RNG）、validation_mlm.json（固定 seed mask 的 loss 与 masked_tokens）、embeddings.npy（每条真实段落的 mean-pooled normalized 编码）、run.json。独立检查 MLM 梯度更新与 finite loss、padding 不参与平均、embedding coverage/shape/归一化、fresh process 重载 embedding 一致和 CUDA forward/backward。不要求小模型重现全 Wikipedia BERT-Large 的准确率。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
