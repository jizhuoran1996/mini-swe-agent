# BUILDv1-B01 · 构建并交付 LLVM/Clang 本机 C/C++ 工具链

Build and deliver a native LLVM/Clang C/C++ toolchain

**主工程**：[LLVM / Clang](https://github.com/llvm/llvm-project)  
**组别**：编译工具链与语言运行时　**规划规模**：超大型　**实施优先级**：advanced

**语言**：C++；C；Python  
**构建系统**：CMake；Ninja；TableGen；lit  
**Canonical goal**：`llvm-native-toolchain-source-build`

## Agent 任务目标

从干净源码生成可供另一个项目使用的 x86_64 Clang/LLD 工具链，交付完整安装目录并证明新工具链能够编译、链接和运行 C/C++ 多文件程序。

## 官方工作流与派生方式

llvm-project CMake/Ninja build, check-llvm-unit, check-clang and check-lld

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置符合该 revision 要求的 C/C++ bootstrap 编译器、CMake、Ninja、Python 及系统 C/C++ 头文件与库；源码包括 cmake/third-party。

## 需要完成的工作

- 配置 X86 目标和 clang/lld 子项目，完整编译并安装。
- 运行 LLVM 单元、Clang 和 LLD 回归测试；保存 lit 的发现、执行、失败及 unsupported 数。
- 用安装目录中的 clang/clang++/ld.lld 构建独立消费者并交付可重用工具链归档。

## 目标范围

本机 X86 后端、Clang C/C++ 前端、LLVM 工具与 LLD ELF 链接器；标准 C/C++ 运行库使用声明的宿主依赖。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT/llvm" -B "$BUILD_ROOT" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DLLVM_ENABLE_PROJECTS="clang;lld" -DLLVM_TARGETS_TO_BUILD=X86 -DLLVM_INCLUDE_TESTS=ON -DCLANG_INCLUDE_TESTS=ON
```

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 将完整 INSTALL_ROOT 与配置/版本清单归档到 ARTIFACT_ROOT；保留依赖布局。

### Official Tests

```bash
ninja -C "$BUILD_ROOT" check-llvm-unit check-clang check-lld
```

## 官方测试选择

- **reference**：check-llvm-unit + check-clang + check-lld
- **rationale**：覆盖底层库、前端语义和链接路径；不运行外部 LLVM test-suite 或 GPU 设备测试。
- **counts**：解析 lit 总数与 unsupported；空套件、缺失 check 目标或意外跳过核心测试均失败。

## 独立消费者验收

- 在源码/构建树之外用 INSTALL_ROOT/bin/clang++ 和 -fuse-ld=lld 编译一个包含静态库与异常处理的多文件 C++ 夹具，并运行断言。
- 检查编译器 realpath、--version、链接日志及实际链接器路径；系统自带 clang/ld 不能代替产物。
- 用新 clang 编译 C 程序并比较确定性输出；检查 ELF 架构。

## 交付物

- toolchain.tar.gz 安装树
- CMakeCache 与源码/依赖清单
- lit 结果和完整构建日志
- 消费者二进制及验收记录

## 后续使用

新请求提供另一个小型 CMake 消费者项目；用已交付工具链在新的 build 目录完成构建与测试，不重新下载或编译工具链。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：X86 + clang；不启用 lld
- **tests**：check-llvm-unit 与 check-clang
- **deliverable**：可运行的本机 Clang 安装树

### Reference：正式参考配置

- **scope**：X86 + clang/lld
- **tests**：check-llvm-unit/check-clang/check-lld
- **deliverable**：C/C++ 编译和 ELF 链接工具链

### Extended：扩展范围

- **scope**：增加 AArch64、RISCV 代码生成后端，保持 Linux X86 host；可加入 check-llvm
- **tests**：对应代码生成回归；外国架构产物只做对象/反汇编验收
- **deliverable**：同一工具链的更多目标支持

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。
- 单独冻结 LLVM_PARALLEL_LINK_JOBS，避免 link 并发随宿主核数隐式变化；后端列表固定。

## 预期资源形态

- cpu_compilation
- large_link_steps
- generated_sources
- many_processes
- file_metadata
- large_build_workspace

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。

## 离线依赖准备

- 完整预载 llvm-project revision 和所有测试依赖；禁用编译器对象缓存。
- 不调用联网依赖安装；宿主 C/C++ 运行库列入依赖清单。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 产物包含选定前端、工具和 linker，版本/源码身份对应本轮。
- 官方测试达到冻结非空集合的通过条件。
- 独立 C 与 C++ 消费者均确实使用新工具链并得到正确结果。

## 应拒绝的负例

- 系统 clang 被 PATH 误选而本轮工具链缺失。
- 只构建 LLVM 核心库、未交付 Clang 或 lld。
- 测试被整体标记 unsupported，或安装包遗漏共享库。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- llvm-project 单一 monorepo；Clang/LLD 是本任务模块，不另外计项目。
- Rust/部分 ML 工程可能复用 LLVM 依赖，应在跨组统计记录共享血缘。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。

## 官方来源

- [B_LLVM_BUILD] [Getting Started with LLVM](https://llvm.org/docs/GettingStarted.html) — 检查位置：Getting the Source Code and Building LLVM; CMake options; install and check-subproject targets
- [B_LLVM_TEST] [LLVM Testing Infrastructure Guide](https://llvm.org/docs/TestingGuide.html) — 检查位置：Unit and Regression tests

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
