# GPUv1-C02：为真实照片修复指定区域

为真实照片修复指定区域
用 CUDA StableDiffusionInpaintPipeline /models/stable-diffusion-v1-5--stable-diffusion-inpainting，fp16，512×512，12 steps，guidance=7.5。mask白色区域生成，黑色保护区域最终与输入逐像素一致（生成结果按 mask composite）。不是无条件生成；应把 image 和 mask 真实送给模型。入口 python solution/main.py run --input input --output output；另支持相同 run 入口对新的 requests.jsonl 处理。输出 images/{id}.png、index.jsonl、run.json，记录原输入 hash、模型、seed、steps、device、同步耗时。独立检查 coverage、图像、GPU denoiser、fresh request 和种子重放。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
