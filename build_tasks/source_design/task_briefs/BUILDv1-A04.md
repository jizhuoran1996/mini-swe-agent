# BUILDv1-A04 · 构建并验证 HTTPS 客户端开发包

Build and validate an HTTPS client development package

**主工程**：[curl](https://github.com/curl/curl)  
**组别**：原生基础库与命令行工具　**规划规模**：中型　**实施优先级**：pilot

**语言**：C；Perl；Python (optional tests)  
**构建系统**：CMake；Make or Ninja  
**Canonical goal**：`build-test-install/curl`

## Agent 任务目标

从源码交付 curl 和 libcurl，使新客户端能访问给定本地 HTTP/HTTPS 服务，正确处理重定向、认证和上传，并提供可复查测试结果。

## 官方工作流与派生方式

CMake testdeps/tests with TFLAGS keyword selection and local runtests.pl fixtures

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 显式构建 CLI、共享/静态 libcurl 与测试依赖，要求 OpenSSL TLS 后端。
- 以官方 HTTP/HTTPS/file 关键词得到固定测试列表，使用上游本地服务完成协议验证。
- 安装后通过新 libcurl consumer 实际访问本轮回环 HTTPS 端点，交付工具和开发元数据。

## 目标范围

curl + libcurl；参考 HTTPS 使用预装 OpenSSL，依赖及启用协议按 feature lock 固定；不包含默认公网访问。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DBUILD_TESTING=ON -DBUILD_CURL_EXE=ON -DBUILD_SHARED_LIBS=ON -DBUILD_STATIC_LIBS=ON -DCURL_USE_OPENSSL=ON
```

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

```bash
cmake --build "$BUILD_ROOT" --target testdeps --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 归档 CLI、开发库、CMake/pkg-config 导出与协议特性列表。

### Official Tests

- TFLAGS="HTTP HTTPS file" cmake --build "$BUILD_ROOT" --target tests

- 最小调通可使用 TFLAGS="1 2 3" cmake --build "$BUILD_ROOT" --target tests；不得用此三条替代参考测试集。

## 官方测试选择

- **reference_keywords**：HTTP；HTTPS；file
- **harness**：tests/runtests.pl via official tests target; TFLAGS supplies keywords.
- **concrete_core_cases**：test1: HTTP GET；test2: GET with Basic auth；test3: POST with authentication and response framing
- **rationale**：多数交互使用上游本地 server fixture；冻结解析后的 test IDs 和 required features，记录因能力不满足而跳过的用例。
- **network_policy**：外部 DNS/第三方服务用例在实例准入时识别，参考列表仅含已预置的本地路径。

## 独立消费者验收

- 新 CMake consumer 用安装的 CURL::libcurl，完成 GET/重定向、POST 与 HTTPS 证书校验。
- 服务器使用固定测试 CA 和本轮动态端口；必须同时核对服务端收到的请求和响应体。
- 错误 CA、连接拒绝和缺失对象应返回约定错误；不能使用 insecure 选项掩盖 TLS 问题。

## 交付物

- curl/libcurl 安装包及 curl -V 特性记录
- 固定 test IDs 与官方结果
- consumer 源码及本地服务协议记录

## 后续使用

- **request**：使用已安装客户端库下载后续指定工件，核对 hash，并上传一个小结果文件到同一本地验收服务。
- **state**：保留开发包、CA 与服务绑定；新请求地址从本轮 manifest 解析。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

完整 CLI/库及 test1–test3，作为本地 HTTP 调通配置。

### Reference：正式参考配置

相同完整产物，加 HTTP/HTTPS/file 官方关键词套件和本地 TLS consumer。

### Extended：扩展范围

显式启用 HTTP/2 或额外官方协议测试；预装相应服务器/依赖并扩大固定 test IDs。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- configure_probes
- parallel_native_compile
- static_shared_link
- test_server_processes
- local_sockets

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。
- 允许非特权回环 TCP 端口和本地测试服务器；主机测试并发需端口隔离。

## 离线依赖准备

- 预装 OpenSSL、libpsl、zlib 和实际启用后端开发包，Perl 及所选测试要求的本地 server 程序。
- 预置 CA/cert fixtures；缺少 Perl 会导致 CURL_BUILD_TESTING 被关闭，必须在 configure 结果中拒绝此情况。

## 回放与状态

- 每次默认回放均从相同源码和依赖状态重新编译；记录的模型等待不替代编译、链接或测试。
- 等待真实进程和测试子进程结束；保留 build tree、临时文件、退出码与产物，下一步依赖本轮完成。
- 测试端口、PID 与临时路径绑定本轮值；时间戳/build ID 导致的字节差异不默认视为功能失败。

## 最终 oracle

- 独立记录源码版本、配置、安装清单与产物身份；禁止系统预装同名库/程序替代。
- 测试 inventory 必须非空，冻结选择并记录 discovered/selected/executed/skipped/failed；错误或空套件不能因返回 0 通过。

## 应拒绝的负例

- 删除必需安装产物后新 consumer 必须失败，不能从系统路径补回。
- 取消测试、错误版本或未经声明跳过必测项，必须被验收拒绝。

## Builder 实施工作

- 绑定正式 release/commit、源与依赖 hash，并解析匹配工具链。
- 实现安装身份检查和独立 consumer，冻结测试清单与环境所需能力。
- 真实构建、采集及参考画像后再分配资源标签；当前规模级别为规划。

## 源码血缘

- primary_project: curl；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_CURL_BUILD] [curl CMake installation guide](https://github.com/curl/curl/blob/master/docs/INSTALL-CMAKE.md) — 检查位置：Build options, consumer linking, Useful build targets
- [A_CURL_TEST] [curl test harness selection](https://github.com/curl/curl/blob/master/tests/runtests.pl) — 检查位置：enabled/disabled keyword parsing, test selection and result accounting
- [A_CURL_CASE] [curl HTTP GET fixture](https://github.com/curl/curl/blob/master/tests/data/test1) — 检查位置：HTTP keyword, HTTP server, request and response oracle

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
