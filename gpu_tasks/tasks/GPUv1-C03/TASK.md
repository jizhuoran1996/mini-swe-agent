# GPUv1-C03：把真实照片的边缘约束转换成新素材

把真实照片的边缘约束转换成新素材
从输入图片计算 Canny (100,200) 边缘，加载 ControlNetModel /models/lllyasviel--sd-controlnet-canny 加 /models/stable-diffusion-v1-5--stable-diffusion-v1-5 的 StableDiffusionControlNetPipeline。CUDA fp16，512×512，12 steps，guidance=7.5，conditioning_scale=1。保存 control/{id}.png 以及生成图。mask 字段不用于本题。入口 python solution/main.py run --input input --output output；另支持相同 run 入口对新的 requests.jsonl 处理。输出 images/{id}.png、index.jsonl、run.json，记录原输入 hash、模型、seed、steps、device、同步耗时。独立检查 coverage、图像、GPU denoiser、fresh request 和种子重放。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
