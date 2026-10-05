# GPUv1-D06：为完整道路短片交付逐问题理解目录

input/requests.jsonl包含完整16帧VKITTI2短片中均匀8帧及3个设计者问题。真实CUDA Qwen2.5-VL-3B-Instruct BF16 AutoProcessor把所有sampledframes作为有序多图上下文（允许实际video processor），不能只处理首帧，max_pixels每帧<=65536，greedy最多128新token每题。入口 run --input input --output output；输出 answers.jsonl包含videoID/questionID/answer/token_ids/used_frame_ids、run.json；infer --input JSONL --output DIR 支持新帧序列和新问题。独立检查8帧覆盖、3题覆盖、visionencoder真CUDA、fresh输入、生成重算；时间理解正确性人工/独立oracle另报，不能声称长视频VideoMME通过。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
