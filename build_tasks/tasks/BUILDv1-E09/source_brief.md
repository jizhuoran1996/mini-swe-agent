# BUILDv1-E09 · 构建 esbuild 本机工具并验收打包接口

Build esbuild and verify its installed bundling interfaces

**主工程**：[esbuild](https://github.com/evanw/esbuild)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：小型　**实施优先级**：pilot

**语言**：Go；TypeScript；JavaScript  
**构建系统**：Make；Go；Node.js scripts  
**Canonical goal**：`build.esbuild.native-cli-api`

## Agent 任务目标

从 esbuild 源码编译本机 binary，运行 Go 及 JS API 的官方测试，并交付一个独立工程可以实际调用的 CLI 与 JS 适配包。

## 官方工作流与派生方式

esbuild Makefile / esbuild build and test installation script

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

Linux x86_64 Go binary 和 JS adapter；默认不运行完整跨平台/浏览器/外部大项目 end-to-end CI。

## 构建与测试入口

### Configure / Generate

- 冻结 Go、Node 与依赖缓存；使用普通 Go 编译路径，不触发源码下载并重编 Go toolchain 的发布扩展。

### Build

- make esbuild；目标实际执行 CGO_ENABLED=0 go build ./cmd/esbuild 并生成版本源文件。

### Package / Install

- 按 scripts/esbuild.js 的本地库构建和 installForTests 路径打包 JS adapter；将本轮 binary 复制至 INSTALL_ROOT/bin。

- 消费者显式使用安装目录的 ESBUILD_BINARY_PATH，禁止从网络安装平台预编译 binary。

### Official Tests

```bash
make test-go
```

```bash
make js-api-tests end-to-end-tests plugin-tests
```

## 官方测试选择

- **reference**：Makefile test-go、js-api-tests、end-to-end-tests、plugin-tests 目标。
- **rationale**：同时覆盖编译器内部、CLI 协议和 JS service API；官方测试可能再次编译 binary，必须作为实际工作计时。

## 独立消费者验收

- 独立目录从本轮安装路径调用 CLI，把固定 TS/JS 多模块程序打包并执行，核对结果和 metafile 输入集合。
- 从本轮 JS adapter 发起 build/transform；ESBUILD_BINARY_PATH 指向 INSTALL_ROOT 内本轮 binary，核对服务子进程路径。
- 错误语法、缺失 import 必须产生相应错误；拒绝依赖外部 esbuild service。

## 交付物

- 本机 binary、JS adapter 包、构建与测试清单、独立 consumer 打包结果。

## 后续使用

利用已经安装的 JS adapter 启动一个 context，对消费者的有效源修改执行 rebuild 并验证新结果；这属于消费者工作，不伪装成本工程源码增量编译。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

make esbuild + make test-go + 独立 CLI consumer。

### Reference：正式参考配置

增加 JS adapter、API/e2e/plugin 官方测试和独立 JS consumer。

### Extended：扩展范围

增加预装依赖后的 source-map/type/Node WASM 官方测试；完整 test-all 需单独声明浏览器与平台依赖。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- go_compilation
- native_binary
- subprocess_rpc
- parallel_tests
- file_resolution
- package_installation

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- Go module 源码 cache 可预装；本轮目标 Go build cache 与测试结果缓存为空。Node scripts 所需依赖预装，官方 installForTests 中本地 npm pack/install 仍实际执行。

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

- primary_project:https://github.com/evanw/esbuild
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。
- reference 不要求 Makefile 中自定义 Go 编译器的发布分支；默认不是跨平台 npm release 构建。

## 官方来源

- [E_ESBUILD_MAKE] [esbuild Makefile](https://github.com/evanw/esbuild/blob/main/Makefile) — 检查位置：esbuild; test-go; js-api-tests; end-to-end-tests; plugin-tests; test-common
- [E_ESBUILD_INSTALL] [esbuild build and test installation script](https://github.com/evanw/esbuild/blob/main/scripts/esbuild.js) — 检查位置：buildBinary; buildNeutralLib; installForTests

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
