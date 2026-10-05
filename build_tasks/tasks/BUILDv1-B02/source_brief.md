# BUILDv1-B02 · 自举构建 GCC C/C++ 编译器与运行库

Bootstrap GCC C/C++ and its runtime libraries

**主工程**：[GCC](https://gcc.gnu.org/git/gcc.git)  
**组别**：编译工具链与语言运行时　**规划规模**：超大型　**实施优先级**：advanced

**语言**：C++；C；Tcl；Shell  
**构建系统**：Autoconf；GNU Make；DejaGnu  
**Canonical goal**：`gcc-native-bootstrap-install`

## Agent 任务目标

交付一个从源码自举生成的本机 C/C++ 编译器及配套 libstdc++，使下游工程能够使用同一套编译器、链接配置和运行库完成开发构建。

## 官方工作流与派生方式

GCC native 3-stage bootstrap and DejaGnu compiler tests

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置 bootstrap C/C++ 编译器、binutils、GMP/MPFR/MPC、构建所需生成器及 DejaGnu/Expect/Tcl；不在计时阶段运行 download_prerequisites。

## 需要完成的工作

- 独立于源码目录配置 C/C++ 与单一 64 位 ABI，执行完整三阶段自举。
- 运行本机 C execute 与 C++ dg 回归选择，保存 .sum/.log 及预期/非预期结果。
- 安装编译器及运行库，并在隔离消费者目录验证二者实际被使用。

## 目标范围

Linux x86_64 C/C++ 前端、libgcc、libstdc++ 和本机构建支持；默认关闭 multilib，避免隐式依赖 32 位用户空间。

## 构建与测试入口

### Configure / Generate

- 在空 BUILD_ROOT 中执行 "$SRC_ROOT/configure" --prefix="$INSTALL_ROOT" --enable-languages=c,c++ --disable-multilib

### Build

```bash
make -C "$BUILD_ROOT" -j"$BUILD_JOBS"
```

- reference 保持默认 bootstrap，不加 --disable-bootstrap。

### Package / Install

```bash
make -C "$BUILD_ROOT" install
```

- 归档 INSTALL_ROOT 与 configure 参数、stage 构建记录和运行库清单。

### Official Tests

```bash
make -C "$BUILD_ROOT/gcc" -j"$TEST_JOBS" check-gcc RUNTESTFLAGS="execute.exp"
```

```bash
make -C "$BUILD_ROOT/gcc" -j"$TEST_JOBS" check-g++ RUNTESTFLAGS="dg.exp"
```

## 官方测试选择

- **reference**：GCC execute.exp 与 G++ dg.exp，使用 native unix target board
- **rationale**：执行测试检验生成代码，C++ dg 集合覆盖编译诊断和语言行为；不要求远程开发板。
- **counts**：按 DejaGnu PASS/XFAIL/XPASS/FAIL/UNSUPPORTED 分类；已知结果须按固定 revision 显式记录。

## 独立消费者验收

- 用新 gcc/g++ 编译 C 和包含 STL、线程与异常的 C++ 夹具并运行。
- 检查 -dumpmachine、编译器 realpath 和 runtime 搜索路径；必要时仅对消费者设置指向新 libstdc++ 的库路径。
- 解析加载映射，确认新 libstdc++ 被加载；只报告 compiler --version 不足以验收。

## 交付物

- gcc-toolchain.tar.gz
- bootstrap 和安装清单
- DejaGnu .sum/.log
- 消费者与运行库来源报告

## 后续使用

利用已安装的编译器和 libstdc++ 构建一个独立共享库及调用程序，验证库边界上的异常和对象行为。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：同一 C/C++ 目标，显式 --disable-bootstrap 的单次源码构建
- **tests**：C execute 与官方 old-deja.exp=9805* C++ 子集
- **deliverable**：完整 C/C++ 安装树；标明非 bootstrap

### Reference：正式参考配置

- **scope**：C/C++ 三阶段 bootstrap
- **tests**：execute.exp 与 dg.exp
- **deliverable**：完整自举编译器和运行库

### Extended：扩展范围

- **scope**：增加 Fortran 前端和 libgfortran
- **tests**：在上述基础上加入 check-fortran 的本机选择
- **deliverable**：同一 GCC 项目的 C/C++/Fortran 工具链

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。
- 冻结启用语言与 target board；bootstrap 阶段次数作为实例协议固定，不按完成速度缩减。

## 预期资源形态

- compiler_bootstrap
- sustained_cpu
- large_build_workspace
- linker_memory
- many_test_processes
- file_metadata

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。

## 离线依赖准备

- GMP/MPFR/MPC 等使用固定本地安装或完整配套源码；检查配置未回退到另一份系统库。
- 预置测试工具及 native 系统头文件；基础 profile 不需网络、root、交叉设备或 GPU。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 三阶段自举完成且比较阶段未被跳过；核心依赖和编译器版本正确。
- 声明的官方测试确实执行并达到固定 acceptance。
- 消费者证明新编译器及新 C++ runtime 能协同工作。

## 应拒绝的负例

- 以系统 GCC 完成消费者，但安装产物为空。
- reference 使用 --disable-bootstrap 或复用旧 stage 对象。
- C++ 产物误用旧 libstdc++ 导致假通过。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- GCC 单项目，多个语言前端属于其规模维度。
- GCC 与 binutils 为不同上游项目；binutils bootstrap 依赖的复用在环境清单说明。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。
- 全 C++ dg 集合可能较长；正式 task timeout 由参考运行确定，超时不能静默缩减测试。

## 官方来源

- [B_GCC_CONFIG] [Installing GCC: Configuration](https://gcc.gnu.org/install/configure.html) — 检查位置：--enable-languages; --disable-multilib; installation prefix
- [B_GCC_BUILD] [Installing GCC: Building](https://gcc.gnu.org/install/build.html) — 检查位置：Building a native compiler
- [B_GCC_TEST] [Installing GCC: Testing](https://gcc.gnu.org/install/test.html) — 检查位置：Running the testsuite; selective tests; RUNTESTFLAGS

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
