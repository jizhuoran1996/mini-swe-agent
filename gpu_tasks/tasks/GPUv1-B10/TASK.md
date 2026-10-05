# GPUv1-B10：适配可重载的户外单目米制深度模型

真实VKITTI2 RGB与对应米制depth，12train/4heldout，392×126。初始化 /models/depth-anything--Depth-Anything-V2-Metric-Outdoor-Small-hf，用AutoImageProcessor和AutoModelForDepthEstimation，CUDA微调至少12次更新、每train图进入一次；允许冻结backbone只训练depthhead；loss=valid像素(mean abs(predicted_depth-target_depth))，valid为0.1<depth<80米，预测双线性插值原图尺寸。保存标准HFcheckpoint、optimizer/step/RNG训练状态、predictions.npy(4,126,392)米制float32、run.json；入口 train --input input --output output，predict --checkpoint PATH --input validation.jsonl --output NPY新进程重载。独立检查真实metric head、标注参与梯度、有限权重更新和predictioncoverage、CUDAbackward、hiddenAbsRel/RMSE另报。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
