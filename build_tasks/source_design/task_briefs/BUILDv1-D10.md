# BUILDv1-D10 · 构建并验证 Envoy 代理发行二进制

Build and qualify an Envoy proxy distribution

**主工程**：[Envoy](https://github.com/envoyproxy/envoy)  
**组别**：数据库与基础设施软件　**规划规模**：超大型　**实施优先级**：advanced

**语言**：C++；C；Protocol Buffers；Python；Go build helpers  
**构建系统**：Bazel；Bzlmod/declared repository dependencies  
**Canonical goal**：`build.install.verify.envoy`

## Agent 任务目标

从锁定的 Envoy 源码与依赖构建代理发行二进制，运行官方 HTTP 测试，并交付能够验证配置、转发请求及处理本地上游的可用包。

## 官方工作流与派生方式

Envoy bazel developer build、envoy-static target 与 HTTP unit-test labels。

## 初始环境

- 固定版本的完整源代码、声明的子模块和测试数据已预置；目标项目的对象文件、已编译库、测试结果和安装目录为空。
- 编译器、引导工具及第三方依赖来源与版本写入输入清单；依赖缓存和本任务产物缓存分别管理。

## 需要完成的工作

- 预置与源码一致的 Bazel、Clang/libc++、语言工具链和 repository 内容，确保目标项目没有 action cache 或远端执行结果。
- 编译 envoy-static，执行两个已检查的 HTTP Bazel 测试目标并保留 BEP/XML。
- 将产物移到独立目录，用本地上游和客户端检验路由、header 与错误响应。

## 目标范围

Envoy 上游正式静态入口二进制及两个 HTTP 测试；不构建整个 //test/... 或要求 Kubernetes/远程 xDS。

## 构建与测试入口

### Configure / Generate

- 使用源树 .bazelversion/.bazelrc 与官方兼容工具链；依赖获取前置，声明 repository cache/vendor/distdir，构建时禁止公网。

- 固定本地执行策略、BUILD_JOBS 和 TEST_JOBS；不启用远程执行、远程 action cache 或从 CI 拉二进制。

### Build

- 在 SRC_ROOT 执行 bazel build -c opt --jobs="$BUILD_JOBS" //source/exe:envoy-static

### Package / Install

- 收集 bazel-bin/source/exe/envoy-static，保存为发行包 bin/envoy，附本地配置模板、NOTICE、动态依赖与 build metadata。

### Official Tests

- 在 SRC_ROOT 执行 bazel test -c opt --jobs="$BUILD_JOBS" --local_test_jobs="$TEST_JOBS" --cache_test_results=no --test_output=errors //test/common/http:header_map_impl_test //test/common/http:codec_client_test

- 若环境仅有 IPv4，使用官方 --test_env=ENVOY_IP_TEST_VERSIONS=v4only 并在所有比较中固定；IPv6 子集差异明确记账。

## 官方测试选择

- **official_entrypoints**：//test/common/http:header_map_impl_test；//test/common/http:codec_client_test
- **selection**：两个源 BUILD 中实际定义的 envoy_cc_test；Bazel test cache 禁用，保存测试运行及案例列表。
- **rationale**：目标足够明确且无需外部控制面；主二进制保留实际大规模依赖、代码生成与链接成本。

## 独立消费者验收

- 以归档中的 bin/envoy 验证固定的静态 bootstrap 配置，检查 --version 和二进制身份。
- 在私有高位 loopback 端口启动本地 HTTP fixture 上游和 Envoy，用新客户端检查两条路由、header 传播及上游错误处理。
- 记录 ready、请求和退出事件，确认消费者使用本轮产物；结束后确认本 session 进程和监听端口释放。

## 交付物

- Envoy 发行二进制与配置/依赖 manifest
- 两个 Bazel target 的 BEP/XML、构建日志及未缓存测试记录
- 独立消费者 bootstrap、请求期望表和实际结果

## 后续使用

用同一交付二进制验证并运行新增静态路由配置，完成新后端路径的本地客户端验收。

## 可选增量变化

- **default**：False
- **kind**：optional_legitimate_patch
- **binding_status**：builder_must_bind_patch_before_collection
- **description**：主任务是干净构建。若增加增量场景，先冻结具有功能意义的上游补丁或已验证配置变更、受影响目标和对应验收；保留同一任务 ID。仅 touch/no-op 不作为独立任务。

## 同一任务的规模配置

### Core：最小完整交付

构建 envoy-static 与 header_map_impl_test，进行单路由本地消费者。

### Reference：正式参考配置

增加 codec_client_test 和多路由/错误处理消费者，保持正式单体二进制。

### Extended：扩展范围

将测试范围扩展到已枚举的 //test/common/http/... 或已绑定 integration target；需要额外能力时独立准入，不盲跑全 CI。

## 可控变量

- 固定实际目标与测试集合；编译并行度和测试并行度独立记录。
- 干净构建为基线；缓存、优化级别和增量模式作为实验场景，不能作为新任务计数。
- 实际资源分类依据参考画像；不预设编译耗时、峰值内存或 syscall 数量。

## 预期资源形态

- very-large Bazel graph
- protobuf code generation
- C++ templates
- hermetic toolchain
- large final link
- repository metadata
- many build processes
- HTTP tests

## 后端能力要求

- Linux x86_64、普通用户、可写工作目录、真实子进程与文件锁；所需 ABI 和工具链随实例固定。
- 允许声明的 Bazel local/processwrapper-sandbox 策略所需进程与文件操作；若选择 linux-sandbox/user namespace，作为显式能力条件，不静默回退。
- 本地 loopback 与普通用户监听；测试对 IPv4/IPv6 的要求固定。

## 离线依赖准备

- 源代码、子模块、依赖、测试 fixture 与工具链在计时前准备；正式构建禁止隐式访问公网。
- 目标项目由源码重新编译；预置工具/依赖的许可、校验和与来源单列。
- 预获取 hermetic Clang、Go、Python、CMake/Make/Ninja 及模块扩展输出；只保留源/toolchain repository 缓存，清空 Envoy 对象/action cache。
- Bzlmod 与 legacy WORKSPACE 路径按锁定源码选择一种；校验离线预热没有漏掉执行平台依赖。

## 回放与状态

- 后续打包和验收依赖真实编译、链接及测试结束；后台子进程必须纳入本 session 生命周期。
- 保存源码、构建树和安装目录的关系；本轮端口、PID 和临时路径重新绑定。
- 默认按功能和来源验证产物，时间戳、链接 build-id 和归档元数据不要求跨次逐字节一致。

## 最终 oracle

- 核对源版本、构建配置、实际产物路径和功能范围，拒绝系统预装版本或源树导入替代产物。
- 记录官方测试的发现、选择、执行、跳过和失败数量，选择集为空或要求的功能被全部跳过均不通过。
- 在独立消费者目录使用本轮安装包或二进制，检查实际结果和错误处理；消费者验证耗时单独记账。

## 应拒绝的负例

- 用系统预装版本替换本轮产物；只留下日志而无可用安装文件。
- 过滤器未匹配测试或依赖缺失导致全部跳过，却报告成功。
- Bazel 从远程 cache 命中 Envoy 主产物；两个 target 只返回 cached 成功；测试被误指向其他 build configuration。

## Builder 实施工作

- 固定源码 revision、工具链和完整依赖快照；实现 source/install/test 产物清单。
- 将官方命令包装为资源可追踪的任务环境，绑定测试集合、端口及真实完成事件。
- 首次真实构建时冻结官方测试的精确数量、消费者期望结果与合理 timeout；不存在实测资源数值。

## 源码血缘

- Envoy 单体二进制与所选 extensions 为一个主工程；BoringSSL/protobuf/Abseil/LLVM 等共享依赖单列。
- 构建中的 Bazel execution sandbox 与被测云 sandbox 是两层，执行策略必须随场景固定。

## 与已有任务的关系

与此前资源任务可能共享软件来源；本题交付源码构建与测试后的工程产物，区别于只运行该软件处理数据。

## 范围说明

- 规模标签是规划，实际成本待参考构建画像；本任务不要求外部生产部署或跨宿主集群。
- envoy-static 名称不保证无任何运行时系统依赖，必须实际检查并随包声明。

## 官方来源

- [D_ENVOY_BUILD] [Envoy Bazel developer guide](https://raw.githubusercontent.com/envoyproxy/envoy/main/bazel/README.md) — 检查位置：Building envoy, envoy-static path, individual tests, cached tests and IPv4/IPv6 selection
- [D_ENVOY_TEST] [Envoy HTTP unit-test build targets](https://raw.githubusercontent.com/envoyproxy/envoy/main/test/common/http/BUILD) — 检查位置：header_map_impl_test, codec_client_test, async_client_impl_test and utility targets

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
