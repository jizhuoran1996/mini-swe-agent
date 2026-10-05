# BUILDv1-B03 · 构建并验收 ELF 汇编、链接与归档工具

Build and validate an ELF assembler, linker and archive toolkit

**主工程**：[GNU binutils](https://sourceware.org/git/binutils-gdb.git)  
**组别**：编译工具链与语言运行时　**规划规模**：中型　**实施优先级**：pilot

**语言**：C；C++；Tcl  
**构建系统**：Autoconf；GNU Make；DejaGnu  
**Canonical goal**：`binutils-native-elf-toolkit-build`

## Agent 任务目标

从源码交付一套可操作本机 ELF 文件的 assembler、linker、archive 和 inspection 工具，完成对象生成、静态归档、链接以及调试信息检查。

## 官方工作流与派生方式

binutils-gdb configure; all-binutils/all-gas/all-ld; DejaGnu checks

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置 C/C++ 编译器、Make、Bison/Flex/texinfo（锁定源码需要时）、DejaGnu/Expect/Tcl。

## 需要完成的工作

- 在独立构建目录关闭 GDB/GDBserver，完整构建选中的 binutils、gas 和 ld。
- 执行三个对应官方测试目标，安装工具并验证真实二进制处理链。

## 目标范围

Linux x86_64 native as、ld.bfd、ar、nm、objcopy、objdump、readelf 及支撑库；不构建调试器。

## 构建与测试入口

### Configure / Generate

- 在 BUILD_ROOT 执行 "$SRC_ROOT/configure" --target=x86_64-linux-gnu --prefix="$INSTALL_ROOT" --disable-gdb --disable-gdbserver

### Build

```bash
make -C "$BUILD_ROOT" -j"$BUILD_JOBS" all
```

### Package / Install

```bash
make -C "$BUILD_ROOT" install
```

- 归档安装树、目标格式清单与工具版本。

### Official Tests

```bash
make -C "$BUILD_ROOT" -j"$TEST_JOBS" check-binutils check-gas check-ld
```

## 官方测试选择

- **reference**：check-binutils/check-gas/check-ld 的 native 默认集合
- **rationale**：分别验证对象操作、汇编与链接；相关测试不需要 ptrace 或实际调试目标。
- **counts**：读取各 .sum/.log；固定默认 target，保留 XFAIL/UNSUPPORTED。

## 独立消费者验收

- bootstrap C 编译器只生成汇编输入；使用新 as 和 ar 生成对象与库，再显式选择新 ld 完成链接并运行结果。
- 用新 readelf/objdump 检查符号、节和架构；用新 objcopy 分离调试信息后再次运行程序。
- 核对每一工具实际路径和版本；目标库遗漏或使用系统 ld 均失败。

## 交付物

- binutils-install.tar.gz
- 原始对象/归档/可执行文件与调试附件
- 官方测试摘要
- 端到端工具来源清单

## 后续使用

对新交付的另一组对象文件执行归档更新和链接，交付保留调试附件的精简发布包。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：本机 binutils/gas/ld
- **tests**：check-binutils/check-gas 与 ld-shared/shared.exp
- **deliverable**：完整基础 ELF 工具包

### Reference：正式参考配置

- **scope**：完整 native 工具集合
- **tests**：三个组件全部 native 回归集合
- **deliverable**：对象、链接和调试处理工具包

### Extended：扩展范围

- **scope**：--enable-targets=all 增加对象格式支持
- **tests**：native 回归加冻结外国格式 fixture 检查
- **deliverable**：更多格式的 inspection 工具；不宣称一个 gas 构建支持所有架构

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。
- 冻结启用组件与 --enable-targets；对象格式扩展不能换算成外国架构执行覆盖。

## 预期资源形态

- native_compilation
- many_small_test_processes
- metadata_operations
- object_file_io
- moderate_linking

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。

## 离线依赖准备

- 预置完整选定 release 的 binutils-gdb 源码和测试工具。
- 无需联网获取 GNU 文档或外部调试目标；所有 fixture 本地固定。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 工具身份和 ELF target 正确；三类官方测试非空。
- 由新工具处理的消费者能运行且符号/调试附件满足合同。

## 应拒绝的负例

- 错误启用 GDB 使范围与声明不符。
- as/ld 不匹配目标或消费者经系统工具绕过。
- strip/objcopy 后产物损坏、安装缺少实际 linker。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- binutils-gdb monorepo 中只选择 binutils/gas/ld；不把子工具算多个项目。
- 构建流程来自维护者公开工作流，绑定具体 release 后需复核目标仍存在。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。

## 官方来源

- [B_BINUTILS_HOME] [GNU Binutils](https://sourceware.org/binutils/) — 检查位置：Tool descriptions and obtaining source
- [B_BINUTILS_WORKFLOW] [Lightning talk notes on binutils](https://sourceware.org/pipermail/binutils/2021-January/115029.html) — 检查位置：Build; Test

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
