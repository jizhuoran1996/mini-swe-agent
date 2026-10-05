# BUILDv1-A08 · 构建多编码正则与 JIT 开发包

Build a multi-encoding regular-expression and JIT package

**主工程**：[PCRE2](https://github.com/PCRE2Project/pcre2)  
**组别**：原生基础库与命令行工具　**规划规模**：中型　**实施优先级**：standard

**语言**：C  
**构建系统**：CMake；Make or Ninja  
**Canonical goal**：`build-test-install/pcre2`

## Agent 任务目标

构建支持 8/16/32 位字符和 JIT 的 PCRE2 安装包，交付命令行搜索与可嵌入 API，并验证 Unicode 捕获及错误输入。

## 官方工作流与派生方式

Official CMake quickstart, character-width options and registered CTest programs

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 预置版本匹配的 JIT 子模块，编译三种代码单元宽度、POSIX 层、pcre2grep 和测试程序。
- 运行 RunTest/RunGrepTest 对应 CTest、JIT 和 POSIX 官方验证。
- 新应用分别链接各宽度接口，核对 Unicode 匹配及 JIT 功能确实存在。

## 目标范围

8/16/32 位实现、JIT、POSIX 兼容接口及 grep；同一源代码以真实支持宽度形成多个 native 目标。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DPCRE2_BUILD_PCRE2_8=ON -DPCRE2_BUILD_PCRE2_16=ON -DPCRE2_BUILD_PCRE2_32=ON -DPCRE2_SUPPORT_JIT=ON -DPCRE2_BUILD_TESTS=ON -DPCRE2_BUILD_PCRE2GREP=ON
```

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 归档三种宽度的库、POSIX 库、头文件和 pcre2grep。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -N
```

```bash
ctest --test-dir "$BUILD_ROOT" --output-on-failure --parallel "$TEST_JOBS"
```

## 官方测试选择

- **reference**：pcre2_test；pcre2_grep_test；pcre2_jit_test；pcre2posix_test
- **rationale**：使用源码 testdata 检查普通匹配、命令行、JIT 及 POSIX 语义；记录 RunTest 内部各宽度分组。
- **requirements**：JIT 子模块须预置；若 JIT 未编译或测试被删除不得把剩余套件报作完整参考。

## 独立消费者验收

- 新 C consumer 分别声明 PCRE2_CODE_UNIT_WIDTH=8/16/32，使用本轮对应库检查捕获位置、UTF 输入和无匹配情况。
- 调用 JIT 配置与编译接口并实际匹配，不能以仅成功链接作为 JIT 验收。
- pcre2grep 从新工作区筛选固定文本文件，结果与独立预期行集合一致。

## 交付物

- 多宽度 PCRE2 开发包
- 四类官方套件及内部 case 统计
- Unicode/JIT consumer 和 grep 验收结果

## 后续使用

- **request**：使用已交付三种编码接口解析后续日志，并返回匹配结果与非法表达式诊断。
- **state**：仅复用安装包和编译好的 consumer；保留 JIT/编码功能声明。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

完整 8 位库及 grep，JIT 关闭，运行相应官方套件。

### Reference：正式参考配置

完整三宽度、JIT、POSIX、grep 及全部对应测试。

### Extended：扩展范围

固定官方压缩输入支持或重建字符表特性，并运行对应测试；工具链优化单独作为情景。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- multi_target_c_compile
- shared_source_multiple_widths
- linking
- unicode_tables
- jit_test_execution

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。
- 参考配置允许 JIT 所需的可执行内存映射；不支持时标记能力不兼容，不能静默退回解释器。

## 离线依赖准备

- 预置 SLJIT 子模块和源码 testdata、Python3、CMake/Ninja。
- 冻结 zlib/bzip2/readline 等可选支持；所有 testdata 在本地。

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

- primary_project: PCRE2；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_PCRE_README] [PCRE2 quickstart and consumer API](https://github.com/PCRE2Project/pcre2/blob/main/README.md) — 检查位置：Quickstart / pcre2_compile consumer / JIT submodule
- [A_PCRE_BUILD] [PCRE2 non-Autotools build guide](https://github.com/PCRE2Project/pcre2/blob/main/NON-AUTOTOOLS-BUILD) — 检查位置：CMake tests and Python runner section
- [A_PCRE_CMAKE] [PCRE2 character widths and test targets](https://github.com/PCRE2Project/pcre2/blob/main/CMakeLists.txt) — 检查位置：PCRE2_BUILD_PCRE2_8/16/32, PCRE2_SUPPORT_JIT and add_test

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
