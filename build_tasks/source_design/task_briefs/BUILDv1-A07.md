# BUILDv1-A07 · 构建带 TLS 支持的事件驱动库

Build an event-driven library with TLS support

**主工程**：[libevent](https://github.com/libevent/libevent)  
**组别**：原生基础库与命令行工具　**规划规模**：中型　**实施优先级**：standard

**语言**：C；Python (test/code generation)  
**构建系统**：CMake；Make or Ninja  
**Canonical goal**：`build-test-install/libevent`

## Agent 任务目标

交付 libevent 核心、线程和 TLS 扩展开发包，并证明新程序可以处理并发本地请求、计时器和有序退出。

## 官方工作流与派生方式

Official CMake/verify workflow and actual EVENT__DISABLE_* options

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 构建完整共享与静态库、样例及测试，要求检测到 OpenSSL。
- 运行来源 verify 目标并记录各 event backend/regress 结果。
- 安装后编译新的 event loop 消费程序，以回环请求与 timer 验收，后续继续使用该安装包。

## 目标范围

event_core、event_extra、event_pthreads、event_openssl 及来源样例/测试；OpenSSL 为预装依赖。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DEVENT__LIBRARY_TYPE=BOTH -DEVENT__DISABLE_TESTS=OFF -DEVENT__DISABLE_SAMPLES=OFF -DEVENT__DISABLE_OPENSSL=OFF
```

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 归档核心/extra/pthreads/openssl 库、头文件和导出配置。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -N
```

```bash
cmake --build "$BUILD_ROOT" --target verify
```

## 官方测试选择

- **reference**：官方 verify 目标，CMake 生成 verify_tests 脚本；内部包括适用的 test_* 和 regress。
- **rationale**：覆盖 buffer/event、网络与线程交互，而不是只跑安装示例。
- **capabilities**：固定 epoll/poll/select 等实际可用后端；verify 会清理 EVENT_NO* 环境设置，因此不能靠环境变量静默禁用某个失败 backend。
- **counting**：同时保存 CTest inventory、regress 子测试数和逐项 skip 原因。

## 独立消费者验收

- 新 C consumer 使用 event_base、bufferevent 和 timer 完成多个固定回环请求，核对响应内容及退出时所有连接关闭。
- 以安装的 event_openssl 完成受控 TLS 请求并校验测试 CA。
- 运行时映射和安装清单必须指向本轮构建产物。

## 交付物

- libevent 多组件开发包
- 配置/verify 报告
- 事件驱动 consumer 与本地协议结果

## 后续使用

- **request**：使用已安装开发包构建另一个小客户端，并让现有服务完成新一批请求后有序关闭。
- **state**：允许保留服务进程、事件循环及已安装库，后续命令须等待真实 ready。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

完整核心/extra/pthreads 库与来源基础检查；显式不带 TLS。

### Reference：正式参考配置

共享和静态完整组件、TLS、samples 与 verify。

### Extended：扩展范围

加入已预装的其他官方 TLS 后端或官方回归特性，固定特性表；不重复计算为新题。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- configure_probes
- native_library_compile
- codegen
- event_loop_tests
- process_and_socket_activity

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。

## 离线依赖准备

- 预装 OpenSSL、zlib、Python3、CMake 及 C 工具链；不允许 AUTO 探测造成后端间功能不同。
- 保存源码测试数据，本地监听端口隔离；外部 DNS 项在实例固定名单中标记。

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

- primary_project: libevent；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_EVENT_BUILD] [libevent build overview](https://github.com/libevent/libevent) — 检查位置：README: CMake Unix and verify
- [A_EVENT_CMAKE] [libevent CMake options and tests](https://github.com/libevent/libevent/blob/master/CMakeLists.txt) — 检查位置：EVENT__LIBRARY_TYPE, EVENT__DISABLE_TESTS, EVENT__DISABLE_OPENSSL, verify, install

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
