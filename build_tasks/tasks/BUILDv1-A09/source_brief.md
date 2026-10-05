# BUILDv1-A09 · 构建 HTTP/2 开发包与本地工具链

Build an HTTP/2 development package and local toolchain

**主工程**：[nghttp2](https://github.com/nghttp2/nghttp2)  
**组别**：原生基础库与命令行工具　**规划规模**：中型　**实施优先级**：standard

**语言**：C；C++23；Go (optional integration)  
**构建系统**：CMake；Make or Ninja  
**Canonical goal**：`build-test-install/nghttp2`

## Agent 任务目标

构建 libnghttp2 与 HTTP/2 客户端/服务器工具，交付一个可安装包并用本地 HTTP/2 传输和 HPACK API 消费验证协议实现。

## 官方工作流与派生方式

Official build requirements plus CMake options, main/failmalloc and check test target

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 明确启用 app、静态库及测试，避免默认 shared-only 构建使测试消失。
- 编译完整 C 库与 nghttp/nghttpd/nghttpx/h2load 工具；构建并执行来源 main/failmalloc 测试。
- 安装后使用本轮 nghttpd/nghttp 在回环链路传输固定资源，并编译独立 HPACK consumer。

## 目标范围

HTTP/2 C library plus nghttp/nghttpd/nghttpx/h2load；默认关闭 HTTP/3、eBPF 与 mruby 扩展。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DENABLE_LIB_ONLY=OFF -DENABLE_APP=ON -DBUILD_SHARED_LIBS=ON -DBUILD_STATIC_LIBS=ON -DBUILD_TESTING=ON -DENABLE_EXAMPLES=OFF -DENABLE_HPACK_TOOLS=OFF -DENABLE_DOC=OFF -DENABLE_HTTP3=OFF
```

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

```bash
cmake --build "$BUILD_ROOT" --target main failmalloc --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 归档 libnghttp2、头文件、元数据与实际构建工具。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -R "^(main|failmalloc)$" --output-on-failure
```

- 若使用上游 check 目标，先确认其注册列表不额外引入未预置的 integration tests。

## 官方测试选择

- **reference**：main；failmalloc
- **rationale**：main 包含 frame/stream/session/HPACK/ALPN 等库测试；failmalloc 验证分配失败处理；两者在源码被 EXCLUDE_FROM_ALL，需显式编译。
- **core**：完整 library-only 构建，同样保留静态库和上述测试。
- **extended**：官方 integration-tests/make it 仅在 Go 模块预载和端口 3009 已隔离的独立 profile 使用。

## 独立消费者验收

- 独立 C 程序通过 nghttp2 HPACK deflate/inflate 接口往返固定头字段，检查顺序和内容。
- 安装的客户端与服务器在本地实际协商 HTTP/2，检验多个资源响应内容和协议标识。
- consumer 依赖及工具加载路径均限定于本轮 install；HTTP/1.1 回退不能满足 HTTP/2 验收。

## 交付物

- HTTP/2 开发包与 CLI 安装归档
- main/failmalloc 分项结果
- HPACK consumer 及本地传输报告

## 后续使用

- **request**：使用已安装服务端暴露后续提供的资源集合，并由新客户端验证 HTTP/2 响应。
- **state**：保留工具和服务配置；服务 ready 与端口来自本轮控制器。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

完整 libnghttp2 C 库、静态/共享产物与 main/failmalloc。

### Reference：正式参考配置

增加真实 C++ HTTP/2 应用并做本地 consumer。

### Extended：扩展范围

增加官方 Go proxy 集成套件或 HPACK tools/examples；各自预置实际依赖。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- c_cpp_compile
- protocol_parser_tests
- allocation_failure_tests
- local_server_lifecycle
- link_memory

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。
- 非特权本地 sockets；当前上游应用需要 C++23，README 明确列出 GCC >=14 或 Clang >=19。

## 离线依赖准备

- 预装匹配的 C/C++23 工具链、OpenSSL、libev、zlib 及来源测试 munit 子模块。
- BUILD_TESTING 在上游依赖 BUILD_STATIC_LIBS，必须都设为 ON 并验收非空测试。
- 扩展 Go integration 依赖在采集前锁定并离线预取，不能运行时联网拉取。

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

- primary_project: nghttp2；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_NGHTTP_README] [nghttp2 build and test guide](https://github.com/nghttp2/nghttp2/blob/master/README.rst) — 检查位置：Requirements, source build, --enable-app, unit and integration tests
- [A_NGHTTP_OPTIONS] [nghttp2 CMake feature options](https://github.com/nghttp2/nghttp2/blob/master/CMakeOptions.txt) — 检查位置：ENABLE_APP, ENABLE_LIB_ONLY, BUILD_STATIC_LIBS, BUILD_TESTING
- [A_NGHTTP_TEST] [nghttp2 CMake unit tests](https://github.com/nghttp2/nghttp2/blob/master/tests/CMakeLists.txt) — 检查位置：main, failmalloc, add_dependencies(check)

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
