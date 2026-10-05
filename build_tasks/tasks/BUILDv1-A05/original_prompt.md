# BUILDv1-A05 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

交付从源码构建的 OpenSSL CLI、libcrypto 和 libssl，使全新程序可执行摘要/签名校验及本地 TLS 通信，并给出官方自测证据。

### 提供的环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

### 工程范围

普通 Linux x86_64 OpenSSL 软件与默认 provider；不宣称 FIPS 认证，也不调用公网端点。

### 工作要求

- 在空 build tree 配置指定 Unix 目标和私有配置目录，编译完整软件及生成代码。
- 运行官方普通测试组，显式区分快速本地与 slow group；捕获 TAP 的真实测试数。
- 安装后启动本地 TLS 会话并编译新的 EVP/TLS consumer，确认 provider 和库均来自本轮安装。

### 交付

- OpenSSL 软件安装包
- configure 特性与 provider 清单
- TAP 测试报告
- EVP/TLS consumer 及协议记录

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

request: 用已安装开发包为新的本地服务接入 TLS，并验证指定 CA 与主机名规则。；state: 保留库、provider、测试 CA 和安装配置；证书与端点绑定本轮。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
