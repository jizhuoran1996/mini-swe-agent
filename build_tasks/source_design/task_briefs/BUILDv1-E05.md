# BUILDv1-E05 · 构建本机 Elasticsearch 分发并验收查询

Build a native-host Elasticsearch distribution and verify queries

**主工程**：[Elasticsearch](https://github.com/elastic/elasticsearch)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：超大型　**实施优先级**：advanced

**语言**：Java；Gradle Groovy  
**构建系统**：Gradle wrapper  
**Canonical goal**：`build.elasticsearch.local-distribution`

## Agent 任务目标

构建适用于 Linux x86_64 的 Elasticsearch 分发，通过本地查询实现的官方测试，并从安装目录启动单节点服务接受独立检索验收。

## 官方工作流与派生方式

Elasticsearch testing and packages / Elasticsearch Gradle build structure / Elasticsearch MatchQueryBuilderTests

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

本机 Elasticsearch archive、server 与默认分发模块；不构建全部操作系统包、Docker 镜像或远程云插件集成环境。

## 构建与测试入口

### Configure / Generate

- 锁定 JDK、Gradle wrapper、分发所需 runtime JDK 和 native 组件；只选本机 archive。

### Build

- ./gradlew --offline --no-build-cache clean localDistro

### Package / Install

- 保存 localDistro 输出的本轮归档，解包至 INSTALL_ROOT；不执行全局 assemble。

### Official Tests

- ./gradlew --offline :server:test --tests 'org.elasticsearch.index.query.*' -Dtests.seed=DEADBEEF

## 官方测试选择

- **reference**：server:test 的 org.elasticsearch.index.query.*，包含已核对存在的 MatchQueryBuilderTests。
- **rationale**：有界查询单元测试加上真实安装后 REST 验收；不把全分发平台的测试均算通过。

## 独立消费者验收

- 在 INSTALL_ROOT 启动普通用户单节点，绑定 loopback 动态端口，显式配置本地数据/日志目录与测试凭据。
- 独立 HTTP 客户端创建 index、写入固定文档、refresh、查询并核对 hit IDs 和聚合结果。
- 确认 server build 信息、模块清单和 Java 进程 classpath 属于本次分发；停机重启后复核持久数据。

## 交付物

- 本机 archive、构建来源和模块清单、server 单元测试报告、HTTP 验收记录。

## 后续使用

对本轮持久索引新增字段和文档，再执行新过滤/聚合查询并核对结果；不重新下载发行包。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

只构建 server JAR 与查询包单元测试；交付独立 Java API 验证，明确不是完整服务。

### Reference：正式参考配置

localDistro + query unit suite + 本机 REST consumer。

### Extended：扩展范围

增加已冻结的本地 Java/YAML REST 测试模块；涉及测试集群时限定单宿主并记录节点数。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- composite_gradle_build
- java_compilation
- large_jar_distribution
- native_dependency_staging
- many_test_classes
- local_service_tests

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- 预装 Gradle 依赖、bundled JDK 和该 archive 需要的 native artifacts；这些第三方/预构建组件单独列出，不声称它们都由本任务编译。

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

- primary_project:https://github.com/elastic/elasticsearch
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。
- Elasticsearch 源码和分发涉及多种授权，精确归档的许可证与依赖再分发条款需要随冻结版本核对。
- 服务以非 root 用户运行；测试 profile 不依赖需宿主变更的生产 bootstrap 条件。

## 官方来源

- [E_ES_TEST] [Elasticsearch testing and packages](https://github.com/elastic/elasticsearch/blob/main/TESTING.asciidoc) — 检查位置：Creating packages; Test case filtering; randomized seed
- [E_ES_BUILD] [Elasticsearch Gradle build structure](https://github.com/elastic/elasticsearch/blob/main/BUILDING.md) — 检查位置：Build logic organisation; module types; dependency verification
- [E_ES_QUERY_TEST] [Elasticsearch MatchQueryBuilderTests](https://github.com/elastic/elasticsearch/blob/main/server/src/test/java/org/elasticsearch/index/query/MatchQueryBuilderTests.java) — 检查位置：org.elasticsearch.index.query test package

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
