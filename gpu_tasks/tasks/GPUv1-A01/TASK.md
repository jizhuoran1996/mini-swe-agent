# GPUv1-A01：适配多轮对话模型并交付可重载 checkpoint

为真实 UltraChat 对话适配一个可离线使用的聊天模型。input/train.jsonl 有 64 个 train_sft 对话，input/validation.jsonl 有 16 个互异 test_sft 对话，格式为 id/messages。模型是 /models/HuggingFaceTB--SmolLM2-135M-Instruct；模型 revision 和输入哈希见 manifest。

实现并执行以下入口：
```
python solution/main.py train --input input --output output
python solution/main.py infer --checkpoint output/checkpoint --input input/validation.jsonl --output output/responses.jsonl
```
训练必须在 CUDA 上以自回归交叉熵真实更新模型。对每个训练对话用 tokenizer chat template 渲染，截断到 256 tokens；批大小自由，每个真实对话至少进入一次优化器更新。可以全量微调或 LoRA，但保存完整 HF 可加载权重或标准 PEFT adapter+基础模型引用，tokenizer 和配置。固定 seed，保存 optimizer/scheduler/step/RNG 状态到 output/training_state.pt，支持命令 train 增加 --resume 状态路径和 --steps 额外更新步数继续训练。

验证所有 16 个对话，以 user prompt（截到第一个 assistant 前）生成 1–32 个新 token，交付 responses.jsonl，每行 id/prompt/generated_text/generated_token_ids。对验证文本按同样 template/256 截断作 teacher-forced 评估，记录 output/run.json 的 train_examples、optimizer_steps、seed、loss_before、loss_after、device、训练参数、输入哈希和同步耗时。这里不要求小模型达到原始 7B 模型质量；独立评价要求有限损失、至少一个实际权重变化、完整输入覆盖、输出可重算、恢复后 step 增长和训练继续。禁止直接复制初始模型、生成缓存文本、仅修改 manifest 或只训练验证文本。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
