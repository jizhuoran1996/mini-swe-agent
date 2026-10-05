# BUILDv1-A03 · 构建多格式归档工具和开发包

Build a multi-format archive toolchain and development package

**主工程**：[libarchive](https://github.com/libarchive/libarchive)  
**组别**：原生基础库与命令行工具　**规划规模**：中型　**实施优先级**：standard

**语言**：C  
**构建系统**：CMake；Make or Ninja  
**Canonical goal**：`build-test-install/libarchive`

## Agent 任务目标

构建 libarchive、bsdtar 和 bsdcpio，交付支持声明格式与元数据语义的安装包；用它创建、提取并验证真实目录归档。

## 官方工作流与派生方式

Official CMake build with ENABLE_TEST/TAR/CPIO and discovered regression cases

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 从干净 build tree 生成库及两种 CLI，显式启用测试。
- 运行 libarchive 与 tar/cpio 的 CTest 注册套件；保存特性探测及跳过原因。
- 安装后恢复一个含子目录、硬链接/符号链接和压缩成员的固定工作区，并用 API consumer 检查内容。

## 目标范围

完整上游归档库和 bsdtar/bsdcpio；固定 zlib、bzip2、xz/lzma、zstd 支持以及 ACL/XATTR 策略。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DENABLE_TEST=ON -DENABLE_TAR=ON -DENABLE_CPIO=ON
```

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 归档库、头文件、bsdtar/bsdcpio 和特性清单。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -N
```

```bash
ctest --test-dir "$BUILD_ROOT" --output-on-failure --parallel "$TEST_JOBS"
```

## 官方测试选择

- **reference**：ENABLE_TEST 注册的 libarchive、bsdtar 和 bsdcpio 本机套件。
- **source_registration**：libarchive/test/CMakeLists.txt 使用 DISCOVER_TESTS 生成实际列表。
- **rationale**：覆盖格式解析、流式读写、提取和文件元数据，源码测试 fixture 参与真实运行。
- **capabilities**：不能因某个后端失败临时关闭 ACL/xattr 等特性；特性支持集在对比前冻结。

## 独立消费者验收

- 安装后运行 bsdtar 与 bsdcpio 生成/提取 fixture，按文件内容、相对路径、链接目标和声明权限核对。
- 新 C 程序使用 archive_read_* 枚举成员并计算恢复内容校验，链接到安装前缀。
- 验证共享库和 CLI 身份；损坏归档必须显式失败而非交付部分目录。

## 交付物

- 库与归档 CLI 安装包
- 格式/压缩支持列表
- 官方测试清单和报告
- 归档恢复 fixture 与 API consumer

## 后续使用

- **request**：把已交付工具用于追加提供的归档，恢复出可用目录并核对链接和权限。
- **state**：已安装工具和前轮工作区保留；新输入的结果另存。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

完整库及 bsdtar，使用冻结的 tar/zip 与基础压缩依赖。

### Reference：正式参考配置

增加 bsdcpio 和全部本机库/CLI 回归，启用声明压缩后端。

### Extended：扩展范围

增加可用 ACL/XATTR 等元数据支持及对应官方测试；需要匹配文件系统能力。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- feature_detection
- many_c_translation_units
- archive_link
- filesystem_metadata
- test_file_fanout

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。
- 参考文件系统应支持测试声明的符号链接/硬链接与权限；ACL/XATTR 扩展需独立能力标记。

## 离线依赖准备

- 预装 CMake/Ninja、C 编译器及固定压缩库开发包；不允许探测到不同系统版本后静默切换功能。
- 保留全部上游 encoded archive fixtures 与测试生成工具。

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

- primary_project: libarchive；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_ARCHIVE_BUILD] [libarchive build instructions](https://github.com/libarchive/libarchive/wiki/BuildInstructions) — 检查位置：CMake variables and Git checkout build instructions
- [A_ARCHIVE_TEST] [libarchive CMake regression registration](https://github.com/libarchive/libarchive/blob/master/libarchive/test/CMakeLists.txt) — 检查位置：libarchive_test source list, DISCOVER_TESTS, run_libarchive_test

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
