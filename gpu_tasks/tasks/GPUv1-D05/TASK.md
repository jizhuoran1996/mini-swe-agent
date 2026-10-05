# GPUv1-D05：为真实扫描文档生成问答目录

输入8张真实DocVQA文档与问题，只有image/question。CUDA /models/Qwen--Qwen2.5-VL-3B-Instruct、AutoProcessor、bf16、max_pixels=262144，模型实际接收图片和question，greedy最多64新tokens。入口 python solution/main.py run --input input --output output；输出 answers.jsonl（id/answer/token_ids）、run.json；另 infer --image PATH --question TEXT --output JSON 新文档。全覆盖，视觉encoder CUDA、生成token重算、fresh图片/问题；ANLS参考答案独立评价。不得只用问题文本推理或读取隐藏gold。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
