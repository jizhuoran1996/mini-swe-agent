# BUILDv1-E03 · 构建 Flink 发行包并验收本地流处理

Build a Flink distribution and verify local stream processing

**主工程**：[Apache Flink](https://github.com/apache/flink)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：超大型　**实施优先级**：advanced

**语言**：Java；Scala；JavaScript  
**构建系统**：Maven wrapper  
**Canonical goal**：`build.apache-flink.jvm-distribution`

## Agent 任务目标

构建 Flink 的 JVM 发行包，完成核心库官方测试，并用本轮安装的 runtime 执行一个有界事件流任务，交付可以继续提交程序的本地安装。

## 官方工作流与派生方式

Flink source build README / Flink distribution POM / Flink core POM

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

以 flink-dist 声明的 runtime、clients、streaming 与状态后端分发闭包为目标；默认不增加 Python API、外部 connector 集群和多机 end-to-end 测试。

## 构建与测试入口

### Configure / Generate

- 固定 master 中被选定的不可变 revision；reference 采用 README 的 JDK17/Java17-target 配置，预装前端资产与 wrapper。

### Build

- ./mvnw -o clean package -DskipTests -Djdk17 -Pjava17-target

### Package / Install

- 将 build-target 指向的本轮分发目录实体复制/归档到 INSTALL_ROOT；禁止只交付回指源树的软链接。

### Official Tests

- ./mvnw -o -pl flink-core -am test -Djdk17 -Pjava17-target；该选择覆盖 flink-core 及实际 reactor 依赖的官方测试。

## 官方测试选择

- **reference**：Maven flink-core module 的官方测试，依赖模块测试按 reactor 明确计数。
- **rationale**：实际编译并测试核心类型、序列化和基础接口；安装后的有界 DataStream job 验证 runtime/clients 可协同执行。

## 独立消费者验收

- 从新安装 lib/ 取得编译/运行 classpath，在独立目录构建事件 keyBy/reduce 程序，输入固定有界事件并核对分组累计结果。
- 通过已安装 runtime 的本地执行路径完成 job；本地端口动态绑定，不能提交给预先存在的外部 Flink 集群。
- 若使用本地 JobManager/TaskManager，记录它们的 JAR 来源、ready、job completion 和最终退出。

## 交付物

- Flink 本地发行归档、模块/依赖清单、Maven 测试报告、独立流处理 job 与输出。

## 后续使用

使用相同安装提交第二个有界事件流，检查运行环境可复用且上次任务的结果和状态不会误替代新任务。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

-pl flink-core -am 的完整构建与测试，交付核心 JAR 和独立序列化 consumer。

### Reference：正式参考配置

完整 JVM flink-dist 闭包、core tests 和本地 runtime 验收。

### Extended：扩展范围

增加冻结的 flink-runtime 官方本地测试选择及状态后端场景；不自动扩成 Docker/Kubernetes 集群测试。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- jvm_compilation
- multi_module_jvm
- frontend_assets
- jar_shading
- metadata_operations
- local_service_tests

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- mvnw 分发、Maven artifacts、runtime-web 的前端工具和包、各 state backend 的 native 依赖按 flink-dist 闭包预装。

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

- primary_project:https://github.com/apache/flink
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。

## 官方来源

- [E_FLINK_README] [Flink source build README](https://github.com/apache/flink/blob/master/README.md) — 检查位置：Building Apache Flink from Source; Java 17 profile; build-target
- [E_FLINK_DIST] [Flink distribution POM](https://github.com/apache/flink/blob/master/flink-dist/pom.xml) — 检查位置：distribution dependencies and assembly
- [E_FLINK_CORE] [Flink core POM](https://github.com/apache/flink/blob/master/flink-core/pom.xml) — 检查位置：test dependencies and Maven module configuration

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
