# BUILDv1-B09 · 自举 Rust 编译器、标准库与文档工具

Bootstrap Rust, its standard library and rustdoc

**主工程**：[Rust](https://github.com/rust-lang/rust)  
**组别**：编译工具链与语言运行时　**规划规模**：超大型　**实施优先级**：advanced

**语言**：Rust；C++；C；Python  
**构建系统**：bootstrap x.py；Cargo；CMake；Ninja；compiletest  
**Canonical goal**：`rust-native-toolchain-bootstrap`

## Agent 任务目标

从锁定源码自举并安装本机 rustc、std 和 rustdoc，交付能独立编译普通 Rust 工程与文档的工具链，验证编译成功和应被拒绝的语言案例。

## 官方工作流与派生方式

Rust x.py stage builds/install and compiletest UI/library tests

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 完整预载 Rust 源码、LLVM 子模块、Cargo vendor 数据和该 revision 要求的 stage0 compiler/std/Cargo。
- 预置 C++ 工具链、CMake、Ninja、Python；stage0 是允许依赖，但目标 stage1/stage2 和对象缓存初始不存在。

## 需要完成的工作

- 以配置文件关闭目标 rustc/CI LLVM 下载，编译 LLVM 和本机 Rust 工具链。
- reference 使用 stage2；运行固定 UI 子目录和标准库测试后安装。
- 用交付 rustc/std 编译新程序，并验证错误程序被拒绝；生成可打开的文档。

## 目标范围

Linux x86_64 rustc、标准库和 rustdoc；reference build.extended=false 不额外交付 Cargo；LLVM 为本轮源码编译的 X86 后端。

## 构建与测试入口

### Configure / Generate

- 在 SRC_ROOT 运行 ./configure --set build.extended=false --set build.docs=false --set rust.download-rustc=false --set llvm.download-ci-llvm=false --set llvm.targets=X86 --set install.prefix="$INSTALL_ROOT" --set install.sysconfdir="$INSTALL_ROOT/etc"

- 冻结 stage0 本地路径/缓存、vendor/offline Cargo 配置以及 x86_64-unknown-linux-gnu host/target。

### Build

- 在 SRC_ROOT 运行 ./x.py build --stage 2 -j "$BUILD_JOBS"

### Package / Install

- 在 SRC_ROOT 运行 ./x.py install --stage 2

- 归档完整 INSTALL_ROOT；新 compiler/std/rustdoc 及共享库必须闭合。

### Official Tests

- 在 SRC_ROOT 运行 ./x.py test --stage 2 tests/ui/const-generics library/std --force-rerun

- 不使用 --bless 改写测试预期，也不以 stage0 的测试替代目标 compiler 测试。

## 官方测试选择

- **reference**：tests/ui/const-generics 与 library/std，明确 stage2，并强制重跑
- **rationale**：UI 检查诊断与编译语义，std 检查运行库；避免全工具 CI、调试器和外国架构测试。
- **counts**：解析 compiletest/std 的发现、执行、ignored、失败；空集合或被缓存为 ignored 不满足验收。

## 独立消费者验收

- INSTALL_ROOT/bin/rustc -vV 和 --print sysroot 指向交付物；无 rustup 自动 fallback。
- 直接编译一个含泛型、集合、线程和文件处理的本地程序并运行；另一个违反借用规则的夹具必须编译失败。
- 用新 rustdoc 为消费者生成文档并检查预期条目；不依赖构建树中的悬空符号链接。

## 交付物

- rust-toolchain.tar.gz
- bootstrap.toml/stage0/LLVM/vendor 清单
- UI 与 std 测试报告
- 消费者与 rustdoc 输出

## 后续使用

用交付工具链编译新增的本地 library crate 和调用程序，跨 crate 验证 ABI/泛型行为及运行结果。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：真实源码 stage1 rustc + 对应目标 std/rustdoc；install --stage 1
- **tests**：const-generics UI 的冻结目录集合
- **deliverable**：开发用途工具链，明确 stage1 身份

### Reference：正式参考配置

- **scope**：stage2 rustc/std/rustdoc，LLVM X86 源码构建
- **tests**：const-generics + library/std
- **deliverable**：完整本机工具链安装

### Extended：扩展范围

- **scope**：启用 build.extended=true，加入同仓库 Cargo 等声明工具或增加 LLVM 目标
- **tests**：固定的对应工具本地测试与本机 UI 集合
- **deliverable**：同一 Rust 工具链的扩展配置

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。
- 冻结 bootstrap stage、LLVM targets/link-jobs、Cargo 并行与 RUST_TEST_THREADS；不可下载目标 compiler 来减少成本。

## 预期资源形态

- multi_stage_bootstrap
- very_large_workspace
- llvm_cpp_compilation
- rust_codegen
- linker_memory
- many_compiletest_processes

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。

## 离线依赖准备

- 预载 stage0 工具链 tarballs 和 SHA、源码子模块及 vendored crates；关闭 Cargo 网络。
- rust.download-rustc=false 与 llvm.download-ci-llvm=false 写入最终配置，核验日志未取用目标 CI 二进制。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- reference 的安装 compiler 为 stage2，std 与安装 sysroot 匹配。
- 官方测试确实运行于新 compiler，UI 预期没有被重写。
- 正向/负向消费者及新 rustdoc 都满足合同。

## 应拒绝的负例

- 只运行 stage0 tests 或用 rustup stable 完成消费者。
- 隐式下载目标 rustc/LLVM 代替本轮编译。
- 使用 --bless 修改 golden output，或安装遗漏实际 std/shared libs。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- Rust monorepo及其 LLVM 子模块；LLVM 与 BUILDv1-B01 共享上游血缘，但本任务验收的是 Rust 工具链。
- Cargo 可选扩展属于同一任务 profile。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。
- stage1 与 stage2 的 ABI 和用途不同，报告必须分开；配置与命令要按锁定 revision 解析。

## 官方来源

- [B_RUST_BUILD] [How to build and run rustc](https://rustc-dev-guide.rust-lang.org/building/how-to-build-and-run.html) — 检查位置：bootstrap.toml; stage builds; specific components
- [B_RUST_TEST] [Running rustc tests](https://rustc-dev-guide.rust-lang.org/tests/running.html) — 检查位置：Running a subset; standard library; force-rerun
- [B_RUST_INSTALL] [Building and installing Rust from source](https://github.com/rust-lang/rust/blob/main/INSTALL.md) — 检查位置：Build steps; configure and make
- [B_RUST_CONFIG] [Rust bootstrap.example.toml](https://github.com/rust-lang/rust/blob/main/bootstrap.example.toml) — 检查位置：rust.download-rustc; LLVM build options; install settings

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
