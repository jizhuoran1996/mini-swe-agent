# GPUv1-C04：生成一段可播放的完整视频

生成一段可播放的完整视频
TextToVideoSDPipeline，CUDA fp16，256×256，16 frames，12 steps，guidance=7.5，8 fps，输出 video.mp4 及逐帧 PNG；后续 run --seed 不同生成新视频。统一入口 python solution/main.py run --input input --output output，支持 --seed 覆盖用于后续新请求；按 ID 保存完整媒体和 index.jsonl、run.json（输入/模型引用、参数、实际时长、GPU同步耗时）。输出必须可解码且有限、有非零内容；质量由独立验收报告，不要求调参或 ensemble。支持再次 run 输入新的 requests.jsonl，不能用既有文件作为答案。音频可使用 Transformers/Diffusers 官方 API，禁止调用随机 fixture、静音或伪造输出。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
