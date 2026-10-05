# GPUv1-C06：修复真实受损短片并交付完整视频

input/frames有16帧真实VKITTI2短片的损坏图，input/masks指定需要修复的白区，干净图仅独立验证器可见。CUDA官方ProPainter，源码input/upstream，权重/models/ProPainter，复制源码到solution或output中的可写运行目录，用官方inference_propainter.py、--video input/frames --mask input/masks --width320 --height192 --fp16 --neighbor_length10 --ref_stride10 --subvideo_length16 --save_frames（参数按源--help校验）。权重挂载/链接到该代码weights路径以禁自动下载。入口 python solution/main.py run --input input --output output；交付repaired.mp4、frames/{index}.png、frame_manifest.json和run.json；新run可处理另一个帧/mask目录。保护区最终按mask与input composite，所有帧必须修复，不能复制上一帧/复制损坏输入或读干净图。独立检查帧数/顺序/尺寸/视频解码、保护区pixel一致、真实GPUflow与inpainting，mask区域PSNR/SSIM另报。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
