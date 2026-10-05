# BUILDv1-F08 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码交付 CPU libxgboost 和包含该库的 Python wheel，通过 C++/Python 官方基础测试，证明新的应用能够训练、保存和加载一个小型树模型。

### 提供的环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 固定 dmlc-core 等 submodules、C++ 工具链、OpenMP、GoogleTest、Python 构建依赖，以及仓库的 agaricus 小型测试数据。

### 工程范围

CPU C++ shared library、官方 C++ tests 和 Python wheel；默认无需 CUDA/NCCL/MPI 或 Dask/Spark 集群。

### 工作要求

- 构建 CPU native core 和 testxgboost。
- 按上游 Python 包流程将本轮共享库打入 wheel；核对打包实际使用的 native library。
- 运行官方 tests 并在新 venv 验收模型保存/加载。

### 交付

- libxgboost.so 和本轮 Python wheel。
- CMake/测试报告、打包库来源及模型重载消费报告。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

接收新样本，用交付模型和本轮安装进行预测；可选构建变体才加入新的源码功能补丁。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
