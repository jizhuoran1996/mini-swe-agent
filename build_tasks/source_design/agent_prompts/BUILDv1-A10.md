# BUILDv1-A10 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

交付本轮源码构建的 libgit2，使独立程序可以创建仓库、提交文件、生成差异并检查出指定版本；完成本地回归和安装后验证。

### 提供的环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

### 工程范围

完整 libgit2、示例程序与 offline 测试；公网、SSH 服务和 invasive 大文件/根路径用例不在参考集合。

### 工作要求

- 编译完整库、官方 examples 和 Clar 测试，固定 HTTP/HTTPS/SSH 支持集。
- 执行官方 offline CTest，保存资源 fixture 和逐子测试结果；不要误跑默认注册的 online/invasive 套件。
- 安装后从新 C 工程链接本轮库，创建/更新本地 Git 仓库并与独立预期对象和工作区内容核对。

### 交付

- libgit2 开发包
- offline/Clar 子测试记录
- 独立 repo consumer、仓库 fixture 与对象/工作区验收报告

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

request: 给已交付仓库应用后续文件变更，生成新提交和差异报告，再恢复指定旧版本。；state: 保留仓库对象/refs/index 与安装包；跨调用真实保留并复用工作区。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
