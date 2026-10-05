# BUILDv1-E10 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从 SWC 源码构建 Rust 编译内核和 Node 绑定，通过官方 transform 与 core tests，并交付一套独立 Node 工程可装载的本机编译器安装。

### 提供的环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

### 工程范围

SWC Node @swc/core 加上本轮 Linux x86_64 Rust native binding；不默认开启插件 WASM 全套或其他平台 native binaries。

### 工作要求

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

### 交付

- 可安装 SWC 本机 bundle、JS/native 对应清单、Rust/Node 测试报告、独立 API consumer。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

使用同一安装新增一项 minify/转译请求，检查异步 API 的实际完成和错误传播；内核/绑定进程仍在本 session 生命周期内。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
