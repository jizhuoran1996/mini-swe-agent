# BUILDv1-E07 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从 Rollup 源码构建发布所需 JS、Rust native parser 和 WASM 产物，通过官方 API 测试，交付可在独立目录安装并打包真实模块图的构建工具。

### 提供的环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。
- 依赖环境可含官方 build:js 必需的旧 Rollup bootstrap 工具；dist/、目标 Rust outputs 及对象缓存仍为空，独立 consumer 不继承 bootstrap 模块查找路径。

### 工程范围

Linux x86_64 native parser + ESM/CJS/CLI JS 分发；reference 使用完整 build 而非缺少部分产物的 build:quick。

### 工作要求

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

### 交付

- Rollup tgz、native/WASM/JS 清单、API 测试报告、独立应用打包和运行结果。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

使用同一已安装 Rollup 为消费者新增第二入口并输出共享 chunk，证明产物边界与运行语义正确。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
