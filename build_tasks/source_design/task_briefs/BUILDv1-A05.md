# BUILDv1-A05 · 构建密码与 TLS 软件开发包

Build a cryptographic and TLS development package

**主工程**：[OpenSSL](https://github.com/openssl/openssl)  
**组别**：原生基础库与命令行工具　**规划规模**：中型　**实施优先级**：standard

**语言**：C；Assembly；Perl  
**构建系统**：Configure；GNU Make  
**Canonical goal**：`build-test-install/openssl`

## Agent 任务目标

交付从源码构建的 OpenSSL CLI、libcrypto 和 libssl，使全新程序可执行摘要/签名校验及本地 TLS 通信，并给出官方自测证据。

## 官方工作流与派生方式

INSTALL.md Configure/build_sw/install_sw and test/README.md list-tests/TESTS

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 在空 build tree 配置指定 Unix 目标和私有配置目录，编译完整软件及生成代码。
- 运行官方普通测试组，显式区分快速本地与 slow group；捕获 TAP 的真实测试数。
- 安装后启动本地 TLS 会话并编译新的 EVP/TLS consumer，确认 provider 和库均来自本轮安装。

## 目标范围

普通 Linux x86_64 OpenSSL 软件与默认 provider；不宣称 FIPS 认证，也不调用公网端点。

## 构建与测试入口

### 工作目录

- BUILD_ROOT，调用源目录的 Configure。

### Configure / Generate

```bash
"$SRC_ROOT/Configure" linux-x86_64 --prefix="$INSTALL_ROOT" --openssldir="$INSTALL_ROOT/ssl" --libdir=lib
```

### Build

```bash
make -j "$BUILD_JOBS" build_sw
```

### Package / Install

```bash
make install_sw
```

```bash
make install_ssldirs
```

- 归档 CLI、libcrypto/libssl、provider modules 和配置，写出相对布局清单。

### Official Tests

```bash
make list-tests
```

```bash
make HARNESS_JOBS="$TEST_JOBS" TESTS="-99" test
```

- 扩展执行 make HARNESS_JOBS="$TEST_JOBS" test，包含来源定义的 slow group。

## 官方测试选择

- **reference**：官方 TESTS="-99"：完整普通组，排除上游定义的 slow group 99。
- **core**：使用已验证的 TESTS="test_rsa test_dsa" 调通，仍完整编译软件。
- **extended**：make test 全部来源默认测试组。
- **rationale**：涵盖密码实现、编码、证书与 TLS 协议的本机验证，较大量 native/assembly 和测试二进制编译。
- **requirements**：测试以普通用户运行；随机种子、测试顺序和 HARNESS_JOBS 在实例中冻结。

## 独立消费者验收

- 独立 C 程序通过 EVP 完成固定消息摘要/签名验证，篡改消息必须不通过。
- 本地 TLS client/server 使用固定测试证书完成真实握手与数据交换，核对加载的 libssl/libcrypto 路径。
- 检查 openssl version -a 与 provider 列表；配置目录不能落到系统 OpenSSL。
- 核对 INSTALL_ROOT/ssl/openssl.cnf 已由 install_ssldirs 安装；消费者明确使用私有配置目录，provider 加载规则与 manifest 一致。

## 交付物

- OpenSSL 软件安装包
- configure 特性与 provider 清单
- TAP 测试报告
- EVP/TLS consumer 及协议记录

## 后续使用

- **request**：用已安装开发包为新的本地服务接入 TLS，并验证指定 CA 与主机名规则。
- **state**：保留库、provider、测试 CA 和安装配置；证书与端点绑定本轮。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

完整 build_sw + RSA/DSA 来源测试，用于构建链路调通。

### Reference：正式参考配置

完整软件和除 group99 外的官方自测。

### Extended：扩展范围

完整自测，包括 slow group；可另设官方可选算法特性实例，验收相应能力。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- large_native_library
- assembly_codegen
- many_test_executables
- link_memory
- short_process_fanout

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。

## 离线依赖准备

- 预装 Perl、其来源要求模块、C/assembly 工具链和 Make；固定生成代码所用 Perl 版本。
- 证书与测试资源使用源码自带数据和固定额外 consumer fixture；不下载公共证书链。

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

- primary_project: OpenSSL；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_OPENSSL_BUILD] [OpenSSL installation guide](https://github.com/openssl/openssl/blob/master/INSTALL.md) — 检查位置：Configure, Out of Tree Builds, build_sw, install_sw, prefix and openssldir
- [A_OPENSSL_TEST] [OpenSSL test guide](https://github.com/openssl/openssl/blob/master/test/README.md) — 检查位置：Running Selected Tests / list-tests / TESTS / HARNESS_JOBS
- [A_OPENSSL_INSTALL_TARGETS] [OpenSSL Unix installation targets](https://github.com/openssl/openssl/blob/master/Configurations/unix-Makefile.tmpl) — 检查位置：install_sw and install_ssldirs targets

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
