# BUILDv1-E04 · 构建 Lucene 库并交付可重载索引示例

Build Lucene libraries and verify a reloadable index

**主工程**：[Apache Lucene](https://github.com/apache/lucene)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：大型　**实施优先级**：standard

**语言**：Java  
**构建系统**：Gradle wrapper  
**Canonical goal**：`build.apache-lucene.library-distribution`

## Agent 任务目标

从官方源码构建 Lucene 的搜索库分发，运行核心模块测试，再在源树之外编译一个索引、更新、关闭重开和查询的 Java 程序。

## 官方工作流与派生方式

Lucene build workflow / Lucene testing guide / Lucene build prerequisites

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

Java Lucene 分发；reference 独立 consumer 使用 core、analysis-common、queryparser 的本轮 JAR。不借此声称已构建 Elasticsearch 或 Solr。

## 构建与测试入口

### Configure / Generate

- 使用该 revision README 要求的 JDK 和 Gradle wrapper；声明测试 seed、JVM 数和堆限制。

### Build

- ./gradlew --offline --no-build-cache clean assemble

### Package / Install

- ./gradlew --offline mavenLocal；收集 build/maven-local/ 的本轮 JAR/POM 到 INSTALL_ROOT。

### Official Tests

- ./gradlew --offline -p lucene/core test -Ptests.seed=DEADBEEF

## 官方测试选择

- **reference**：lucene/core 官方默认测试；固定 randomized-testing seed，保存所有测试状态。
- **extended**：官方 gradlew test 的多模块测试；Nightly/额外资源组另声明。
- **rationale**：覆盖索引结构和搜索库；consumer 验证分发依赖及安装可重载性。

## 独立消费者验收

- 独立 Java 编译只解析 INSTALL_ROOT 的 Lucene JAR，记录 class protection-domain 来源。
- 建立固定小型文档索引，验证词项/短语检索与 stored fields；关闭进程重开索引后重新查询。
- 执行一条更新和删除，确认查询结果发生正确变化；禁止复用其他版本已有索引。

## 交付物

- 本地 Maven 库归档、构建与测试报告、独立索引程序及验收索引。

## 后续使用

要求安装后的同一程序为已有索引增加第二批文档，并证明首批数据仍可检索、删除文档不再返回。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

core module assemble/test，交付 core JAR 与直接 API consumer。

### Reference：正式参考配置

全 Java 分发 assemble+mavenLocal，core suite 与 analyzer/queryparser consumer。

### Extended：扩展范围

全模块官方 test 与额外分析器 consumer；不同测试范围按实例区分。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- java_compilation
- many_test_classes
- jar_packaging
- randomized_tests
- filesystem_metadata
- index_state

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- 预装 Gradle、要求的 JDK 以及所选模块依赖；全 check 所需 Perl/Python 等仅在对应 profile 中加入。

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

- primary_project:https://github.com/apache/lucene
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。

## 官方来源

- [E_LUCENE_WORKFLOW] [Lucene build workflow](https://github.com/apache/lucene/blob/main/help/workflow.md) — 检查位置：assemble, module build, mavenLocal
- [E_LUCENE_TESTS] [Lucene testing guide](https://github.com/apache/lucene/blob/main/help/tests.md) — 检查位置：Generic test commands; module tests; seed control
- [E_LUCENE_README] [Lucene build prerequisites](https://github.com/apache/lucene/blob/main/README.md) — 检查位置：Building / Basic steps

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
