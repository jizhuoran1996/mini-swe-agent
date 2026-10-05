# BUILDv1-F09 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码交付可安装的 LightGBM CLI、共享库及头文件，通过官方 C++ 测试，并让独立 C API 应用使用新构建库完成模型加载与预测。

### 提供的环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 锁定源码与 external_libs、C++/OpenMP/CMake/Ninja 和 GTest；提供官方 examples 的小数据和配置，不含 lightgbm 二进制。

### 工程范围

CPU/OpenMP LightGBM CLI 和 C API SDK；Python wheel 可作为扩展，baseline 本身已交付可安装的 native 工程。

### 工作要求

- 完整构建 CLI、共享库和 testlightgbm。
- 安装到用户级 prefix，归档可交付目录。
- 运行官方 C++ 测试；用新 CLI 产生模型，再由新编译 C API consumer 读取。

### 交付

- LightGBM bin/lib/include 安装归档。
- CMake install manifest、C++ tests XML、独立 consumer 源码和执行报告。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

新应用拿到交付 SDK，编译模型预测 consumer 并处理新增数据；复用安装产物而非源码树的可执行文件。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
