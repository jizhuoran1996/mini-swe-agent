# BUILDv1-A02 · 构建 Zstandard 工具与可嵌入压缩库

Build Zstandard tools and an embeddable compression library

**主工程**：[Zstandard](https://github.com/facebook/zstd)  
**组别**：原生基础库与命令行工具　**规划规模**：中型　**实施优先级**：standard

**语言**：C；C++ (optional contrib)  
**构建系统**：GNU Make  
**Canonical goal**：`build-test-install/zstandard`

## Agent 任务目标

交付本机可安装的 zstd CLI 与 libzstd，覆盖流式和字典使用，并使一个全新应用可以链接本轮库处理后续数据。

## 官方工作流与派生方式

README make/check/install plus selected tests/Makefile regression targets

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 编译上游默认 libzstd 与 CLI，安装完整接口和程序。
- 构建并运行官方 CLI、非法字典、legacy 和线程池测试，保留具体子目标结果。
- 新 C consumer 使用本轮库做分块压缩/解压，CLI 重载字典后的输出须可恢复。

## 目标范围

libzstd 共享/静态安装产物及 zstd CLI；参考不包含全平台矩阵、无限 fuzz 或 benchmark 重复压测。

## 构建与测试入口

### 工作目录

- SRC_ROOT

### Configure / Generate

- 无需 configure；冻结编译器、prefix 和上游实际支持的构建开关。

### Build

```bash
make -j "$BUILD_JOBS"
```

### Package / Install

```bash
make prefix="$INSTALL_ROOT" install
```

- 归档私有安装目录及构建参数。

### Official Tests

```bash
make check
```

```bash
make -C tests -j "$TEST_JOBS" test-cli-tests test-invalidDictionaries test-legacy test-pool
```

- 扩展：make -C tests test-zstream test-fuzzer；将来源默认 duration/seed 或显式固定值写入实例。

## 官方测试选择

- **reference**：check；test-cli-tests；test-invalidDictionaries；test-legacy；test-pool
- **rationale**：检查 CLI、向后兼容、字典失败路径与线程池实现，同时构建真实测试程序。
- **extended**：test-zstream；test-fuzzer
- **counting**：分别报告测试目标和脚本/驱动的检查数；固定随机测试预算，不能静默提前截断。

## 独立消费者验收

- 独立编译使用 ZSTD_compressStream2/ZSTD_decompressStream 的 C consumer，正确处理分块结束和帧边界。
- CLI 与 API 分别处理固定文本/二进制 fixture，恢复结果必须相同。
- 记录 CLI 实际路径和 libzstd 运行时加载路径，阻止调用系统 zstd。

## 交付物

- zstd/libzstd 安装包与依赖清单
- 命名测试目标及结果日志
- 流式 consumer 和字典使用示例

## 后续使用

- **request**：利用保留的开发包处理后续提供的分块输入和已有字典，并交付可解压文件。
- **state**：保留安装产物及有效字典；不重新复制上游已有二进制。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

默认完整 CLI/库构建和 make check。

### Reference：正式参考配置

增加 CLI 脚本、legacy、invalidDictionaries、pool 官方测试程序。

### Extended：扩展范围

增加流式和 fuzzer 官方套件的固定预算；性能压测时间单独报告。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- native_compile
- parallel_object_build
- linking
- test_processes
- temporary_file_churn

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。

## 离线依赖准备

- 预装 C 编译器、Make、Python3 和 POSIX 工具；固定 zlib/lzma/lz4 等可选依赖是否启用。
- 测试 fixture 随源码提供；不在计时窗口下载版本历史或外部 corpus。

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

- primary_project: Zstandard；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_ZSTD_README] [Zstandard build instructions](https://github.com/facebook/zstd/blob/dev/README.md) — 检查位置：Build instructions / Makefile / Testing
- [A_ZSTD_TESTMAKE] [Zstandard concrete regression targets](https://github.com/facebook/zstd/blob/dev/tests/Makefile) — 检查位置：check, test-cli-tests, test-invalidDictionaries, test-legacy, test-pool, test-zstream, test-fuzzer
- [A_ZSTD_TESTDOC] [Zstandard testing organization](https://github.com/facebook/zstd/blob/dev/TESTING.md) — 检查位置：Short, medium and long tests

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
