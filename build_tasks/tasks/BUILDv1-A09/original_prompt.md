# BUILDv1-A09 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

构建 libnghttp2 与 HTTP/2 客户端/服务器工具，交付一个可安装包并用本地 HTTP/2 传输和 HPACK API 消费验证协议实现。

### 提供的环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

### 工程范围

HTTP/2 C library plus nghttp/nghttpd/nghttpx/h2load；默认关闭 HTTP/3、eBPF 与 mruby 扩展。

### 工作要求

- 明确启用 app、静态库及测试，避免默认 shared-only 构建使测试消失。
- 编译完整 C 库与 nghttp/nghttpd/nghttpx/h2load 工具；构建并执行来源 main/failmalloc 测试。
- 安装后使用本轮 nghttpd/nghttp 在回环链路传输固定资源，并编译独立 HPACK consumer。

### 交付

- HTTP/2 开发包与 CLI 安装归档
- main/failmalloc 分项结果
- HPACK consumer 及本地传输报告

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

request: 使用已安装服务端暴露后续提供的资源集合，并由新客户端验证 HTTP/2 响应。；state: 保留工具和服务配置；服务 ready 与端口来自本轮控制器。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
