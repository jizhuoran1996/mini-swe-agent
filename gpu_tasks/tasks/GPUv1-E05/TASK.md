# GPUv1-E05：构建可复用的百万向量检索索引

input/base.npy有1000000个128维真实SIFT1M向量，queries.npy有10000个独立source query。实现真实CUDA L2 top10索引，可exact或高召回ANN；所有query必须查询，输出indices.npy(10000,10)和squared_distances.npy，index/保存完整可加载数据库/索引、run.json。入口 python solution/main.py build --input input --output output；query --index output/index --queries PATH --output DIR能处理新查询且无需原输入；serve --index PATH --port PORT，/health、POST /search {vectors:[...],k:10}必须真实CUDA就绪。独立CPU oracle全query recall>=.95、距离和ID一致、32个新扰动query、两轮idle、SIGTERM、重载。可使用PyTorch GPU矩阵计算，分块保持显存预算，不得全N×N。

测试环境：单张 RTX 5090，PyTorch 2.11、Transformers 5.12、NumPy 已提供，使用 python。容器无网络，输入和 /models 只读，源码写 solution/，产物写 output/，最多 24 GiB RAM、6 CPU、8 GiB 工作区。不得搜索隐藏评价器或宿主文件，不得伪造工作、重复样本占位或用无意义 CUDA 张量冒充计算。

本题是正式题的 debug 变体，具体变化见 input/manifest.json；原始规格完整保存在 source_spec.json，不宣称完成 reference-large。提交 solution/main.py、solution/README.md 及规定产物。实际运行后交付；源码必须由求解 agent 编写。
