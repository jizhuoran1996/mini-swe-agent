# BUILDv1-E07 · 构建 Rollup 的 JS 与原生解析器分发

Build Rollup with its JavaScript and native parser artifacts

**主工程**：[Rollup](https://github.com/rollup/rollup)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：大型　**实施优先级**：standard

**语言**：TypeScript；Rust；JavaScript  
**构建系统**：npm；Cargo；napi-rs；wasm-pack；Rollup bootstrap  
**Canonical goal**：`build.rollup.native-js-distribution`

## Agent 任务目标

从 Rollup 源码构建发布所需 JS、Rust native parser 和 WASM 产物，通过官方 API 测试，交付可在独立目录安装并打包真实模块图的构建工具。

## 官方工作流与派生方式

Rollup build and test scripts / Rollup contributor build guide / Rollup package test script

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。
- 依赖环境可含官方 build:js 必需的旧 Rollup bootstrap 工具；dist/、目标 Rust outputs 及对象缓存仍为空，独立 consumer 不继承 bootstrap 模块查找路径。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

Linux x86_64 native parser + ESM/CJS/CLI JS 分发；reference 使用完整 build 而非缺少部分产物的 build:quick。

## 构建与测试入口

### Configure / Generate

- 固定 package-lock、Cargo.lock、rust-toolchain.toml 与 wasm target；目标输出 dist/、Rust target cache 均从空开始。

### Build

- npm run build；该脚本包含 build:wasm、build:ast-converters、release build:napi、build:js 和 build:copy-native。

### Package / Install

- npm pack --ignore-scripts --pack-destination "$ARTIFACT_ROOT"；确认 tgz 包含本轮 dist/*.node 与 JS entry points。

### Official Tests

```bash
npm run test:only
```

```bash
npm run test:options
```

- npm run test:package；此项只检查包依赖元数据，不能替代 consumer 验证。

## 官方测试选择

- **reference**：test:only 对应 mocha test/test.js，以及 options/package 脚本。
- **rationale**：官方外部 API/fixture 测试可覆盖实际新构建；浏览器/全 TS 文档检查作为扩展。

## 独立消费者验收

- 新安装 tgz 的 require/import/CLI 均解析到 INSTALL_ROOT，核对实际装载的 .node 为本轮文件。
- 打包包含 dynamic import、可移除未用导出和 source map 的固定多模块工程；执行产物并核对运行结果及模块图。
- 屏蔽预装 @rollup/rollup-linux-* 发布二进制兜底；缺少新 native 产物必须失败。

## 交付物

- Rollup tgz、native/WASM/JS 清单、API 测试报告、独立应用打包和运行结果。

## 后续使用

使用同一已安装 Rollup 为消费者新增第二入口并输出共享 chunk，证明产物边界与运行语义正确。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

官方 build:prepare 的 Node native + JS 交付及对应 Node API 测试，不声称含完整 WASM/browser 分发。

### Reference：正式参考配置

完整 npm run build 与 test:only/options/package。

### Extended：扩展范围

增加 npm run test:browser、test:typescript 及完整 test:all；浏览器与 Rust/WASM 依赖在环境准备时装载。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- rust_compilation
- typescript_compilation
- cross_language_linking
- wasm_artifacts
- package_metadata
- module_graph_tests

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- npm prepare 可能自动构建目标：依赖准备阶段控制脚本并在基线前移除目标输出；保留必要的官方 prepare:patch，不留下 dist/Rust target 缓存。
- 预装 Rust 声明工具链、rust-src/WASM target、wasm-pack 和 npm dependencies；不在计时阶段执行 rustup update。
- 允许固定的 Rollup devDependency 及其 native parser 作为 bootstrap-only 工具，锁定版本/路径/使用阶段；它们不属于本轮交付产物。consumer 环境与 bootstrap 依赖隔离，只加载新 tgz 中的 dist/*.node。
- 预置匹配 Cargo.lock 的 wasm-bindgen CLI、兼容的 Binaryen/wasm-opt 和 wasm-pack 的查找缓存；固定 CARGO_NET_OFFLINE=true，并验证工具实际命中预置路径。

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

## 源码血缘

- primary_project:https://github.com/rollup/rollup
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。
- Rollup 与其他 JS compiler 共享 bootstrap 工具，按软件血缘记录；官方 test:package 不是完整安装运行验收。

## 官方来源

- [E_ROLLUP_PACKAGE] [Rollup build and test scripts](https://github.com/rollup/rollup/blob/master/package.json) — 检查位置：build, build:napi, build:wasm, build:js, build:copy-native, test:only, files
- [E_ROLLUP_CONTRIB] [Rollup contributor build guide](https://github.com/rollup/rollup/blob/master/CONTRIBUTING.md) — 检查位置：Rust setup; build vs build:quick; test categories
- [E_ROLLUP_PACKAGE_TEST] [Rollup package test script](https://github.com/rollup/rollup/blob/master/scripts/test-package.js) — 检查位置：Entire short script
- [E_ROLLUP_WASM_TOOLCHAIN] [Rollup WASM binding build configuration](https://github.com/rollup/rollup/blob/master/rust/bindings_wasm/Cargo.toml) — 检查位置：wasm-bindgen dependency and release wasm-opt configuration
- [E_WASM_PACK_BUILD] [wasm-pack build implementation](https://github.com/rustwasm/wasm-pack/blob/master/src/command/build.rs) — 检查位置：step_install_wasm_bindgen and step_run_wasm_opt

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
