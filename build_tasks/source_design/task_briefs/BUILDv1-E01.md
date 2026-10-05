# BUILDv1-E01 · 构建 Kafka 发行包并验收事件往返

Build a Kafka distribution and verify event round trips

**主工程**：[Apache Kafka](https://github.com/apache/kafka)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：大型　**实施优先级**：standard

**语言**：Java；Scala  
**构建系统**：Gradle wrapper  
**Canonical goal**：`build.apache-kafka.linux-distribution`

## Agent 任务目标

从给定 Kafka 源码构建可迁移的 Linux 发行包，通过客户端测试，再用本轮安装的单节点 KRaft broker 完成独立生产与消费验收。

## 官方工作流与派生方式

Kafka build, test, release and KRaft instructions / Apache Kafka Quickstart

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

本机 Scala 2.13 Kafka 二进制发行包，包括 broker 脚本及 Java clients；不构建 Docker 镜像或执行多宿主系统测试。

## 构建与测试入口

### Configure / Generate

- 固定选定 revision 的 Java/Scala、Gradle wrapper 和 maxParallelForks/maxScalacThreads；依赖已预装。

### Build

- ./gradlew --offline --no-build-cache clean releaseTarGz

### Package / Install

- 收集 core/build/distributions/ 中本轮 tar.gz，解包至 INSTALL_ROOT；不用预装 Kafka 或 Docker 镜像。

### Official Tests

- ./gradlew --offline clients:test

- core profile 可选择 ./gradlew --offline clients:test --tests RequestResponseTest；reference 执行完整 clients:test。

## 官方测试选择

- **reference**：Gradle clients:test 官方客户端单元测试；保存全部 XML/报告和测试清单。
- **core**：官方 README 的 RequestResponseTest 选择。
- **rationale**：覆盖协议消息、序列化、元数据及客户端实现；另以真实 broker 交付验证补足服务启动路径。

## 独立消费者验收

- 从 INSTALL_ROOT/bin 启动单节点 KRaft；cluster ID、数据目录与 loopback 端口属于本轮绑定。
- 在独立目录编译 Java producer/consumer，classpath 只使用新发行包 clients JAR 和已锁普通依赖；写入唯一 key/value 并检查 partition/offset 与消费内容。
- 核对 broker 进程 JAR 来源及版本，干净停止后重启并重读持久记录。

## 交付物

- 发行 tar.gz、依赖/构建 manifest、客户端测试报告、独立 Java consumer 及事件验收记录。

## 后续使用

后续要求在同一已安装 broker 上新建第二个 topic、写入一批新事件并验证两个 topic 的记录独立，保留原日志状态。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

只构建 clients JAR 并运行 RequestResponseTest 与独立序列化 consumer；不声称包含 broker。

### Reference：正式参考配置

完整 releaseTarGz + clients:test + 单节点端到端验收。

### Extended：扩展范围

增加官方 core:test 或 streams:integration-tests:test 的 RestoreIntegrationTest，在同一宿主执行并冻结本地进程预算。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- jvm_compilation
- scala_compilation
- generated_protocol_sources
- jar_packaging
- local_service_tests
- persistent_build_state

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- 预装 Gradle 分发、Java/Scala 编译依赖与测试依赖；Kafka 自身 JAR/Gradle target build cache 不进入初始状态。

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

- primary_project:https://github.com/apache/kafka
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。

## 官方来源

- [E_KAFKA_README] [Kafka build, test, release and KRaft instructions](https://github.com/apache/kafka/blob/trunk/README.md) — 检查位置：Build a JAR; Run unit/integration tests; Building a binary release; Running a Kafka broker; Common build options
- [E_KAFKA_QUICKSTART] [Apache Kafka Quickstart](https://kafka.apache.org/quickstart) — 检查位置：Quickstart steps 2–5 and 8: standalone KRaft start, topic creation, producing/consuming events, shutdown

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
