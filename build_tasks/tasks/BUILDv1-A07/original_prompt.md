# BUILDv1-A07 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

交付 libevent 核心、线程和 TLS 扩展开发包，并证明新程序可以处理并发本地请求、计时器和有序退出。

### 提供的环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

### 工程范围

event_core、event_extra、event_pthreads、event_openssl 及来源样例/测试；OpenSSL 为预装依赖。

### 工作要求

- 构建完整共享与静态库、样例及测试，要求检测到 OpenSSL。
- 运行来源 verify 目标并记录各 event backend/regress 结果。
- 安装后编译新的 event loop 消费程序，以回环请求与 timer 验收，后续继续使用该安装包。

### 交付

- libevent 多组件开发包
- 配置/verify 报告
- 事件驱动 consumer 与本地协议结果

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

request: 使用已安装开发包构建另一个小客户端，并让现有服务完成新一批请求后有序关闭。；state: 允许保留服务进程、事件循环及已安装库，后续命令须等待真实 ready。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
