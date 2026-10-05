# BUILDv1-A10 · 构建可嵌入 Git 工作区管理开发包

Build an embeddable Git workspace-management package

**主工程**：[libgit2](https://github.com/libgit2/libgit2)  
**组别**：原生基础库与命令行工具　**规划规模**：中型　**实施优先级**：standard

**语言**：C；Python (test generation)  
**构建系统**：CMake；Make or Ninja  
**Canonical goal**：`build-test-install/libgit2`

## Agent 任务目标

交付本轮源码构建的 libgit2，使独立程序可以创建仓库、提交文件、生成差异并检查出指定版本；完成本地回归和安装后验证。

## 官方工作流与派生方式

Official CMake BUILD_TESTS/EXAMPLES with offline Clar test registration

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 编译完整库、官方 examples 和 Clar 测试，固定 HTTP/HTTPS/SSH 支持集。
- 执行官方 offline CTest，保存资源 fixture 和逐子测试结果；不要误跑默认注册的 online/invasive 套件。
- 安装后从新 C 工程链接本轮库，创建/更新本地 Git 仓库并与独立预期对象和工作区内容核对。

## 目标范围

完整 libgit2、示例程序与 offline 测试；公网、SSH 服务和 invasive 大文件/根路径用例不在参考集合。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DBUILD_TESTS=ON -DBUILD_EXAMPLES=ON -DBUILD_CLI=OFF -DUSE_HTTPS=OpenSSL -DUSE_SSH=OFF
```

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 归档库、头文件和 pkg-config/CMake 元数据，附带本轮 examples 与测试报告。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -N -R "^offline$"
```

```bash
ctest --test-dir "$BUILD_ROOT" -R "^offline$" --output-on-failure
```

## 官方测试选择

- **reference**：offline
- **actual_command**：libgit2_tests -v -xonline，来自 add_clar_test；CTest 名称为 offline。
- **rationale**：在源码 resources 上检查对象库、索引、提交、diff、checkout、配置等本地工程能力。
- **inventory**：除 CTest 的 1 个聚合项外，必须解析 Clar 内部测试数量、失败与 skip；只报告 1/1 不能代表完整覆盖。

## 独立消费者验收

- 新 C 程序调用 git_libgit2_init，并在空目录创建仓库、写 blob/tree/commit、修改内容、生成 diff 与 checkout；结束调用 shutdown。
- 使用独立的固定 Git 命令/解析器验收提交树和工作区文件，固定 author/committer/timestamp 后才比较对象 ID。
- 动态链接映射必须指向 INSTALL_ROOT，不能调用预装 libgit2；错误提交引用必须失败。

## 交付物

- libgit2 开发包
- offline/Clar 子测试记录
- 独立 repo consumer、仓库 fixture 与对象/工作区验收报告

## 后续使用

- **request**：给已交付仓库应用后续文件变更，生成新提交和差异报告，再恢复指定旧版本。
- **state**：保留仓库对象/refs/index 与安装包；跨调用真实保留并复用工作区。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

完整库和固定本地 repo/object/index 子集，子集须从绑定版本 Clar inventory 解析。

### Reference：正式参考配置

完整库、官方 examples、全 offline 套件及独立仓库 consumer。

### Extended：扩展范围

启用官方本地 gitdaemon/SSH 集成时预置服务与 credentials；单独准入，不执行公网或根目录 invasive 测试。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- native_c_compile
- generated_test_registry
- many_source_headers
- git_object_files
- metadata_and_checkout

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。

## 离线依赖准备

- 预装 CMake、C 工具链、Python3、OpenSSL/zlib 和固定依赖；Clar 与全部 tests/resources 随源码提供。
- source fixture 仓库的权限/链接/大小写语义冻结，Git 身份配置与时间固定在任务目录。

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

- primary_project: libgit2；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_GIT_README] [libgit2 build and feature guide](https://github.com/libgit2/libgit2/blob/main/README.md) — 检查位置：CMake build, BUILD_EXAMPLES, dependencies and initialization
- [A_GIT_CMAKE] [libgit2 top-level CMake configuration](https://github.com/libgit2/libgit2/blob/main/CMakeLists.txt) — 检查位置：BUILD_TESTS, BUILD_CLI, BUILD_EXAMPLES, USE_HTTP and USE_HTTPS
- [A_GIT_TEST] [libgit2 offline regression suite](https://github.com/libgit2/libgit2/blob/main/tests/libgit2/CMakeLists.txt) — 检查位置：Clar generator, add_clar_test offline/invasive/online
- [A_GIT_CLAR] [libgit2 CTest naming helper](https://github.com/libgit2/libgit2/blob/main/cmake/AddClarTest.cmake) — 检查位置：ADD_CLAR_TEST function

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
