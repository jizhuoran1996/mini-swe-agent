# BUILDv1-A03 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

构建 libarchive、bsdtar 和 bsdcpio，交付支持声明格式与元数据语义的安装包；用它创建、提取并验证真实目录归档。

### 提供的环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

### 工程范围

完整上游归档库和 bsdtar/bsdcpio；固定 zlib、bzip2、xz/lzma、zstd 支持以及 ACL/XATTR 策略。

### 工作要求

- 从干净 build tree 生成库及两种 CLI，显式启用测试。
- 运行 libarchive 与 tar/cpio 的 CTest 注册套件；保存特性探测及跳过原因。
- 安装后恢复一个含子目录、硬链接/符号链接和压缩成员的固定工作区，并用 API consumer 检查内容。

### 交付

- 库与归档 CLI 安装包
- 格式/压缩支持列表
- 官方测试清单和报告
- 归档恢复 fixture 与 API consumer

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

request: 把已交付工具用于追加提供的归档，恢复出可用目录并核对链接和权限。；state: 已安装工具和前轮工作区保留；新输入的结果另存。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
