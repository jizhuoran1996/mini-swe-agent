# BUILDv1-F02 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从冻结 TensorFlow 源码交付 CPU Python 发行包，通过官方 softmax 和 SavedModel 测试，并让新进程加载交付环境中保存的计算图与变量。

### 提供的环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 提供匹配 .bazelversion 的 Bazel、Clang、Python、完整 external repositories/工具链输入和 CPU 配置答案；没有目标 Bazel action cache。

### 工程范围

完整 CPU Python TensorFlow wheel，包括本地产生的 native library 与 SavedModel；不要求 TensorFlow Serving、TPU/GPU kernels 或外部云服务。

### 工作要求

- 根据固定 CPU 配置完成 Bazel wheel 构建。
- 执行已绑定的本地 kernel/SavedModel targets，保留 BEP/XML。
- 在新的安装环境真实导入 native TensorFlow、保存并重载一个固定小模型。

### 交付

- TensorFlow CPU wheel 与 build/test manifest。
- Bazel BEP、测试 XML、实际目标清单。
- 独立 SavedModel 保存/重载报告和输入产物。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

收到新的输入矩阵后在新进程加载已保存模型并计算结果，验证发行包在原构建进程结束后可使用。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
