# GPUv1-C01：交付四张真实扩散模型生成的场景插图

交付四张真实扩散模型生成的场景插图
用 /models/segmind--tiny-sd 的 StableDiffusionPipeline，CUDA fp16，256×256、12 inference steps、guidance_scale=7.5、每行给定 seed。输入 requests.jsonl，全部处理一次，输出 output/images/{id}.png、index.jsonl（id/prompt/seed/image/参数）、run.json。入口 python solution/main.py run --input input --output output；python solution/main.py generate --prompt TEXT --seed N --output PNG 支持新的请求，不能依赖既有输出。同步 GPU 后提交；不可只输出随机噪声或复制图片。独立评价重放一例，同 seed 图像容差，并验证完整覆盖、可解码、CUDA denoiser 真正执行。质量单独记录。本调试使用真实训练过的 distilled SD，不是随机 tiny fixture。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
