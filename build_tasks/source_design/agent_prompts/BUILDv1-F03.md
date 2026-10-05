# BUILDv1-F03 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

交付从源码编译的 CPU jaxlib 和配套 JAX Python wheel，验证 JIT 编译、向量运算和自动微分可在独立环境中工作。

### 提供的环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 预备源码固定的 XLA、Bazel、hermetic Python、requirements_lock 和 LLVM/Clang；未装 jax/jaxlib，未保留 XLA/JIT 目标缓存。

### 工程范围

CPU jaxlib/XLA 与同源码版本 JAX frontend。Python 包装层安装本身不算完成，必须包含本轮编译的 jaxlib native libraries。

### 工作要求

- 实际编译 jaxlib 内含 XLA/CPU 运行时，构建配套 Python frontend wheel。
- 运行固定 lax_numpy 测试并冻结生成用例参数。
- 新环境校验 CPU device、JIT 和 grad，等待计算完成后记录结果。

### 交付

- 匹配的 jax 与 jaxlib 两只 wheel。
- hermetic 工具/依赖锁、XLA 来源、编译配置和日志。
- 官方测试报告及独立 JIT/梯度结果。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

在同一发行环境执行输入形状不同的新函数，检验编译服务和 native runtime 在交付后可处理新的程序。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
