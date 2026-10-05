# GPUv1-C10：把真实照片变成可重载的三维资产

input/object.jpg是真实COCO图片。使用官方TripoSR代码input/upstream和/models/stabilityai--TripoSR/config.yaml、model.ckpt，在CUDA运行真正图像encoder、triplane/decoder，DINO ViT pretrained引用改为本地/models/facebook--dino-vitb16，不能网络下载。提取64^3网格，CPU skimage.measure.marching_cubes可作等价等值面提取（不是GPU模型替代），顶点颜色必须从真实decoder查询，导出asset.glb/mesh.ply；PBR metallic=0 roughness=.5明确默认，其他material不能伪造为模型预测。入口 python solution/main.py run --input input --output output；index.json记录原图hash/transform/模型绑定、mesh顶点面数/material参数；run.json；用MatplotlibAgg或等价CPU渲染三个预览PNG，并支持 inspect --asset output/asset.glb --output JSON 新进程读回检查。禁止用预制球/立方体、只有点云或复制mesh。独立检查模型实际CUDA推理、网格拓扑finite/nondegenerate、GLB可解析、颜色/material和预览存在，重载。三维质量独立报告。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
