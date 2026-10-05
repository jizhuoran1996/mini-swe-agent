# BUILDv1-E08 · 构建 Babel 工具链并验收跨版本转译

Build the Babel toolchain and verify a consumer transformation

**主工程**：[Babel](https://github.com/babel/babel)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：中型　**实施优先级**：standard

**语言**：TypeScript；JavaScript  
**构建系统**：Yarn；Make；Babel bootstrap  
**Canonical goal**：`build.babel.compiler-packages`

## Agent 任务目标

从 Babel monorepo 源码构建 core、CLI、parser、generator 及所需 preset/plugin 包，通过官方 fixtures 并向独立工程交付可执行转译工具链。

## 官方工作流与派生方式

Babel build and test guide / Babel Makefile / Babel core package metadata

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

原生 monorepo Babel 编译器与 CLI/preset 包；发布及远程 npm 操作不在任务范围。

## 构建与测试入口

### Configure / Generate

- 锁定所选 revision 的 Node、Yarn、yarn.lock 和 workspace 依赖；bootstrap-only/依赖准备不得留下 target lib 构建缓存。

### Build

- make build；所有选定 workspace 的 lib 来自本次源码转译。

### Package / Install

- 按 workspace pack 将本轮 @babel/core、@babel/cli、@babel/preset-env 及其 Babel 内部依赖闭包置入 ARTIFACT_ROOT；消费工程使用这些本地 tarball。

- make build-dist 只完成其 Makefile 指定的 distribution 子目标，不能替代 make build。

### Official Tests

```bash
yarn jest babel-core
```

```bash
yarn jest babel-cli
```

```bash
TEST_ONLY=babel-parser make test-only
```

## 官方测试选择

- **reference**：官方 babel-core、babel-cli、babel-parser package tests 与 fixtures。
- **rationale**：覆盖解析、编译 API 和 CLI；Jest 子串匹配的最终套件清单必须冻结。

## 独立消费者验收

- 独立目录安装本地 built tarballs，记录每个 @babel/* 内部依赖的解析路径，不能仅 core 为本地而其余偷用缓存发布版。
- 转译包含 class、async 与模块导出的固定程序到声明 target；执行新输出核对结果并解析 source map。
- 负例语法输入应返回约定 parse failure；结果不允许只是抄写已存在的 fixture 输出。

## 交付物

- Babel workspace tarballs 与闭包锁、官方测试日志、独立转译工程及运行结果。

## 后续使用

对同一消费工程增加另一种官方支持的语法输入，并利用已经安装的工具链重新生成及验收输出。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

完整构建所需 workspace，测试 parser+core，交付 compiler API 消费闭包。

### Reference：正式参考配置

core/CLI/preset 分发闭包与三组官方测试。

### Extended：扩展范围

make build-standalone 与预装的额外 parser/transform fixtures；可扩展全 yarn jest，但不临时克隆语料。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- monorepo_transpilation
- bootstrap_compiler
- many_small_modules
- source_maps
- fixture_tests
- package_dependency_closure

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- 使用该 revision 的 Yarn cache 与 workspace 链接；全 bootstrap 可能触发目标编译，准备快照中应只保留依赖/bootstrap 输入并清空目标 lib 输出。

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

- primary_project:https://github.com/babel/babel
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。

## 官方来源

- [E_BABEL_CONTRIB] [Babel build and test guide](https://github.com/babel/babel/blob/main/CONTRIBUTING.md) — 检查位置：Developing / Setup; make build; package tests
- [E_BABEL_MAKE] [Babel Makefile](https://github.com/babel/babel/blob/main/Makefile) — 检查位置：build, build-dist, bootstrap-only, test-only, build-standalone
- [E_BABEL_CORE] [Babel core package metadata](https://github.com/babel/babel/blob/main/packages/babel-core/package.json) — 检查位置：package entry points/files and workspace dependencies

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
