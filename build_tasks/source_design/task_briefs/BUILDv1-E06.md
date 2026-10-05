# BUILDv1-E06 · 构建 TypeScript 编译器包并验收类型检查

Build a TypeScript compiler package and verify type checking

**主工程**：[TypeScript](https://github.com/microsoft/TypeScript)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：中型　**实施优先级**：pilot

**语言**：TypeScript；JavaScript  
**构建系统**：npm；Hereby；esbuild bootstrap  
**Canonical goal**：`build.typescript.classic-compiler-package`

## Agent 任务目标

从 TypeScript v5.9.3 源码构建 compiler、language server 和声明文件，运行官方编译器测试，再把新生成的 npm 包安装到独立工程完成编译和诊断验收。

## 官方工作流与派生方式

TypeScript v5.9.3 package scripts / TypeScript v5.9.3 Hereby tasks

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

固定经典 TypeScript v5.9.3 的 JS compiler、tsserver 与声明包；不混用当前 main 的 Go 原生工作流。

## 构建与测试入口

### Configure / Generate

- 固定 v5.9.3 与 package-lock.json；预装 npm 指定版本及构建 bootstrap 依赖。

### Build

```bash
npm run clean
```

```bash
npm run build
```

### Package / Install

- 执行已核对 Herebyfile.mjs 的 LKG 任务：本地 node_modules/.bin/hereby LKG，将 built/local 本轮输出置入发布 lib 布局。

- npm pack --ignore-scripts --pack-destination "$ARTIFACT_ROOT"；fresh consumer 从该 tgz 安装。

### Official Tests

- npm test；实际脚本为 hereby runtests-parallel --light=false。

## 官方测试选择

- **reference**：package.json 的 npm test，官方 compiler/language-service 基线测试。
- **core**：Hereby runtests 的冻结 --tests selector，可从官方测试清单选 compiler 子集；采集前记录精确条目。
- **rationale**：既验证编译语义又验证新发行布局；不把生成代码更新为新期望值来消除失败。

## 独立消费者验收

- 独立目录安装本轮 tgz，记录 require.resolve("typescript") 与 bin/tsc 的实际路径。
- 编译包含泛型、模块与声明输出的固定工程，运行产出的 JavaScript 并核对结果。
- 加入独立已知类型错误输入，要求报出约定诊断且返回失败；验收不能调用 bootstrap 的 tsc。

## 交付物

- TypeScript tgz、产物清单、官方 baseline 报告、独立消费工程与诊断输出。

## 后续使用

安装包保持不变，要求为第二个含项目引用的独立工程生成 JS 和 .d.ts，并确认 import 与声明解析正确。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

build:compiler + 非空官方 compiler test 子集，仍交付完整 compiler 包。

### Reference：正式参考配置

npm run build + LKG/pack + npm test 与独立正负验收。

### Extended：扩展范围

加入已冻结的 language-service/server 或浏览器集成测试范围，平台资产预装。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- typescript_compilation
- bootstrap_toolchain
- code_generation
- many_small_files
- compiler_test_corpus
- package_installation

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- TypeScript/esbuild bootstrap 编译工具可以预装，但需与新目标 compiler 身份区分；consumer 只能装载本轮 LKG 后的包。

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

- primary_project:https://github.com/microsoft/TypeScript
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。
- 有意固定 v5.9.3 经典实现；升级到原生 Go 实现时应重新定义该任务实例的源码/构建范围。

## 官方来源

- [E_TS_PACKAGE] [TypeScript v5.9.3 package scripts](https://github.com/microsoft/TypeScript/blob/v5.9.3/package.json) — 检查位置：scripts, files and packageManager
- [E_TS_HEREBY] [TypeScript v5.9.3 Hereby tasks](https://github.com/microsoft/TypeScript/blob/v5.9.3/Herebyfile.mjs) — 检查位置：local, runtests, runtests-parallel, LKG, clean
- [E_TS_LKG] [TypeScript release-layout staging](https://github.com/microsoft/TypeScript/blob/v5.9.3/scripts/produceLKG.mjs) — 检查位置：source=built/local, dest=lib; copyScriptOutputs and copyDeclarationOutputs

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
