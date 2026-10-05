# GPUv1-E06：为真实百万向量生成可复用内容分区

input/vectors.npy 为 SIFT1M 的 1000000 个真实 128 维 float32 描述子。用 CUDA 上的 K-means（K=32，固定 seed，至少一次 Lloyd 更新，最多 20 次，收敛可提前停）对所有向量聚类，批量距离和分配、质心求和必须真实在 GPU 上执行。不要做全量 N×N 距离。输出 output/centroids.npy (32,128)、assignments.npy (1000000,) int32/int64、counts.npy (32,)、run.json（每轮 SSE、seed、同步计时、覆盖数和配置）。空簇需明确处理。
入口：python solution/main.py fit --input input --output output。另支持 python solution/main.py assign --centroids output/centroids.npy --vectors input/vectors.npy --output output/reassigned.npy，不重新训练。最终分配必须针对最终质心。独立验收检查全覆盖、最近质心分配、计数与 SSE 重算、质心是最终簇的均值（或残差相对基线 ≤ 0.02，允许提前停止后的最后一轮偏差）、SSE 比一个总均值质心下降至少 5%，新进程新向量可分配；检查 CUDA 距离与归约内核。不得只聚类前缀后随机分配其余向量。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
