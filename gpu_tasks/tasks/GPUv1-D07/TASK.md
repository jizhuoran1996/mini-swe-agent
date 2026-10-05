# GPUv1-D07：把真实文档页面整理成可复用的 Markdown

用 /models/Qwen--Qwen2.5-VL-3B-Instruct 与 AutoProcessor 的真实image+text输入，CUDA bf16，每张页面生成最多512 tokens，greedy，限制max_pixels=262144。入口 python solution/main.py run --input input --output output；输出每个ID的Markdown、documents.jsonl（id/text/token_ids/图片hash）、run.json；支持 infer --image PATH --prompt TEXT --output JSON 的新页面。真实页面来自OmniDocBench，hidden reference不提供。独立验收全coverage、输出合法、实际vision encoder CUDA、fresh新图片推理；OCR字符误差、阅读顺序/表格质量单独报告。禁止只OCR占位或复制预存文本。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
