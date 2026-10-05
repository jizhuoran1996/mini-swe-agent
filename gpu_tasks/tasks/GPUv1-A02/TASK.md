# GPUv1-A02：训练可复用的偏好对齐对话模型

input/train.jsonl 为 32 个真实 UltraFeedback chosen/rejected 对，validation.jsonl 为 8 个独立 test_prefs 对。基础模型 /models/HuggingFaceTB--SmolLM2-135M-Instruct 已冻结。实现真实 CUDA DPO：基础模型作为固定 reference，策略模型执行梯度更新；assistant response 才计入 log-prob，prompt padding 不计入，长度最多 256，不能截掉 response 后把空值当偏好学习。beta=0.1、固定 seed，全部训练对至少使用一次，可调学习率/epoch。
入口 python solution/main.py train --input input --output output；支持 python solution/main.py evaluate --checkpoint output/checkpoint --input input/validation.jsonl --output output/reloaded.json。交付可由标准 HF/PEFT 加载的 checkpoint/、training_state.pt（optimizer/reference binding/step）、preferences.json（每个验证 ID 的策略与 reference chosen/rejected log-prob，DPO loss 和 preference margin）、run.json。独立检查真实 policy 权重改变、reference 未变、正负样本 mask 正确、8 对完整覆盖、每个 log-prob 可从 checkpoint 重算且 finite、DPO loss 有限及 GPU backward。小实例报告 preference accuracy，不要求替代正式 7B 质量目标。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
