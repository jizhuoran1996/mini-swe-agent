# BUILDv1-E10 · 构建 SWC 原生 Node 扩展并验收转译

Build SWC native Node bindings and verify transformation

**主工程**：[SWC](https://github.com/swc-project/swc)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：大型　**实施优先级**：advanced

**语言**：Rust；TypeScript；JavaScript  
**构建系统**：Cargo；pnpm；napi-rs  
**Canonical goal**：`build.swc.native-node-toolchain`

## Agent 任务目标

从 SWC 源码构建 Rust 编译内核和 Node 绑定，通过官方 transform 与 core tests，并交付一套独立 Node 工程可装载的本机编译器安装。

## 官方工作流与派生方式

SWC contributor workflow / SWC core native package / SWC native binding loader

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

SWC Node @swc/core 加上本轮 Linux x86_64 Rust native binding；不默认开启插件 WASM 全套或其他平台 native binaries。

## 构建与测试入口

### Configure / Generate

- 冻结 Cargo.lock、pnpm-lock、Rust toolchain 与 ECMAScript 子模块；预装 Node 和选测所需脚本，默认选择 Linux x86_64 GNU ABI。

### Build

- pnpm build；root script 进入 packages/core，执行 tsc -d 和 napi release build -p binding_core_node。

### Package / Install

- 把 packages/core 新 JS/.d.ts、运行期依赖和本轮平台 .node 按 binding.js 的本地加载布局归档到 INSTALL_ROOT。

- 这是可安装的本机 bundle；不能只运行普通 npm pack，因为当前 core files 清单不包含本地 .node。也可实现等价的本地 platform package，但必须绑定新 binary。

### Official Tests

```bash
cargo test --offline --locked -p swc_ecma_transforms --all-features
```

```bash
pnpm test:core
```

## 官方测试选择

- **reference**：官方 per-package swc_ecma_transforms tests 和 packages/core 的 rstest。
- **rationale**：Rust 变换和 Node glue 均实际构建测试；fixtures、Deno/wasm 需求按冻结选择预装，不用全 workspace --all 代替有界选择。

## 独立消费者验收

- 从 INSTALL_ROOT 运行独立 Node 程序，记录 core JS 和实际 .node 文件的路径/哈希；禁止 @swc/core-linux-* 的预装版本回退。
- 转译固定 TypeScript/JSX 输入到声明 ECMAScript target，执行可运行输出并验证 source map、导出与错误诊断。
- 关闭源树读取后重复 API 验收，证明安装 bundle 带齐运行期文件。

## 交付物

- 可安装 SWC 本机 bundle、JS/native 对应清单、Rust/Node 测试报告、独立 API consumer。

## 后续使用

使用同一安装新增一项 minify/转译请求，检查异步 API 的实际完成和错误传播；内核/绑定进程仍在本 session 生命周期内。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

本机 core release binding、官方 core Node tests 与独立基础 transform consumer。

### Reference：正式参考配置

core binding 加 swc_ecma_transforms 完整选定测试和类型/source-map consumer。

### Extended：扩展范围

增加明确的 plugin/WASM 构建与测试模块，锁定 wasm target、fixture 与执行器，不跨成 GPU 工作负载。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- rust_compilation
- native_linking
- node_addon
- typescript_wrapper
- large_test_fixtures
- ffi_boundary

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- Cargo crate sources、pnpm store、Node ABI 工具和测试子模块按锁文件预装；Rust target/sccache 和已发布的 SWC native binary 不得充当新产物。

## 回放与状态

- 记录并回放真实构建/测试命令与前序完成依赖；父 shell 返回不代表所有后台任务完成。
- 本轮 PID、临时目录和端口经逻辑绑定解析；所有进程实际退出或按生命周期规则保留。
- 按语义及内容清单验收，构建时间戳/JAR 元数据不要求普遍逐字节一致。

## 最终 oracle

- 产物的项目版本、来源清单、目标范围与安装布局符合 manifest；编译/打包事件覆盖目标源代码。
- 官方测试选择非空且与清单匹配；失败和意外跳过保留，不以空套件退出零作为通过。
- 独立 consumer 的加载路径/服务进程指向 INSTALL_ROOT 内的本轮产物，验证预期正例与负例。

## 应拒绝的负例

- 用预装发布版、旧 JAR/对象缓存或源码路径替代本轮安装产物。
- 空测试选择、隐藏失败、只打包源码而未完成目标构建。
- 缺少约定模块/本地 native 库，或后台测试未完成即宣告成功。

## Builder 实施工作

- 将已检查的来源冻结到不可变提交，完成依赖锁和可离线安装快照。
- 实现产物收集、测试清单与独立 consumer harness，采集一次真实 agent 轨迹。
- 在参考机器运行并测量后确定资源画像与超时；目前的规模等级是设计估计。
- 实现明确包含新 .node 的本机 bundle staging 或本地平台包流程，验证 loader 解析；不能照搬 npm 发布包文件清单后丢失 native 产物。

## 源码血缘

- primary_project:https://github.com/swc-project/swc
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。

## 官方来源

- [E_SWC_CONTRIB] [SWC contributor workflow](https://github.com/swc-project/swc/blob/main/CONTRIBUTING.md) — 检查位置：submodules; JS dependencies; per-package cargo tests
- [E_SWC_CORE] [SWC core native package](https://github.com/swc-project/swc/blob/main/packages/core/package.json) — 检查位置：build/build:dev/build:ts/test; files
- [E_SWC_LOADER] [SWC native binding loader](https://github.com/swc-project/swc/blob/main/packages/core/binding.js) — 检查位置：Linux native-binding resolution branches
- [E_SWC_TRANSFORMS] [SWC transforms crate configuration](https://github.com/swc-project/swc/blob/main/crates/swc_ecma_transforms/Cargo.toml) — 检查位置：features compat/module/optimization/proposal/react/typescript and test dependencies

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
