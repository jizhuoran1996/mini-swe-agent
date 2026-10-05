# BUILDv1-F01 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从提供的 PyTorch 源码交付 CPU wheel，证明其张量运算、自动求导、序列化和 C++ 扩展接口可用于新的应用。主任务完整构建 CPU 框架，不需要训练大模型。

### 提供的环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 依赖包含 Python、C++20 编译器、CMake/Ninja、所选 BLAS/OpenMP、scikit-build-core 与测试组；源码 submodules 已就绪。BUILD_ROOT 对应固定的 CMake build-dir。
- 对已检查的 main 配方固定 BUILD_ROOT=SRC_ROOT/build；若覆盖 scikit-build build-dir 则将该参数写入唯一实例配置。

### 工程范围

Linux x86_64 CPU wheel：ATen、autograd、torch.nn、序列化和 C++ extension headers；reference 包含其普通 CPU kernels，不启用 GPU toolchain。

### 工作要求

- 核对 CPU-only 配置并生成真实 ATen/torchgen 与 native libraries。
- 构建 wheel，安装到独立 venv；运行指定 PyTorch 官方测试。
- 由新消费端做张量/梯度/保存重载检查，随后从同一 wheel 的头文件编译一个小扩展。

### 交付

- CPU torch wheel、构建配置与动态库清单。
- 官方测试报告及独立消费端/扩展构建报告。
- 保留的构建树引用、源依赖锁和产物 hash。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

交付后收到一个使用 torch C++ API 的小扩展源码，为新应用编译并验证该扩展；消费本轮 SDK，不重装公开 wheel。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
