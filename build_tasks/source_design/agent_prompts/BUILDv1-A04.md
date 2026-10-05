# BUILDv1-A04 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码交付 curl 和 libcurl，使新客户端能访问给定本地 HTTP/HTTPS 服务，正确处理重定向、认证和上传，并提供可复查测试结果。

### 提供的环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

### 工程范围

curl + libcurl；参考 HTTPS 使用预装 OpenSSL，依赖及启用协议按 feature lock 固定；不包含默认公网访问。

### 工作要求

- 显式构建 CLI、共享/静态 libcurl 与测试依赖，要求 OpenSSL TLS 后端。
- 以官方 HTTP/HTTPS/file 关键词得到固定测试列表，使用上游本地服务完成协议验证。
- 安装后通过新 libcurl consumer 实际访问本轮回环 HTTPS 端点，交付工具和开发元数据。

### 交付

- curl/libcurl 安装包及 curl -V 特性记录
- 固定 test IDs 与官方结果
- consumer 源码及本地服务协议记录

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

request: 使用已安装客户端库下载后续指定工件，核对 hash，并上传一个小结果文件到同一本地验收服务。；state: 保留开发包、CA 与服务绑定；新请求地址从本轮 manifest 解析。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
