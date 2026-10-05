# BUILDv1-F10 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码交付具有 CPU execution provider 的 ONNX Runtime wheel 和共享库，通过官方运行时测试，并让独立进程加载与执行一个声明的 ONNX 模型。

### 提供的环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 提供匹配源码的 submodules/deps archives、CMake/C++/Python、ONNX/protobuf 和小模型测试 fixtures；没有现成 ONNX Runtime package。

### 工程范围

Linux CPU ONNX Runtime native library、Python binding/wheel、普通 CPU execution provider；默认非 minimal/operator-reduced build。

### 工作要求

- 用官方 build.sh 编译共享库、Python binding 和 wheel。
- 运行固定 CPU runtime/provider/shared-lib 程序。
- 在新安装环境加载本地 ONNX 图，核对输入输出、线程运行和库来源。

### 交付

- ONNX Runtime CPU wheel、共享库和依赖/EP 清单。
- 官方 C++ tests XML、编译日志、独立 ONNX 图消费报告。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

交付后应用加载新的兼容 ONNX 图并处理输入，验证安装包的图加载能力而非仅执行构建时缓存的一个输出。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
