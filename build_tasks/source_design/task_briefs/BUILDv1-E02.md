# BUILDv1-E02 · 构建 Spark SQL 发行包并交付本地分析程序

Build Spark SQL and verify an installed local analytics job

**主工程**：[Apache Spark](https://github.com/apache/spark)  
**组别**：JVM 与 JavaScript 工程　**规划规模**：超大型　**实施优先级**：advanced

**语言**：Scala；Java  
**构建系统**：Maven；Spark build/mvn wrapper  
**Canonical goal**：`build.apache-spark.sql-distribution`

## Agent 任务目标

从 Spark v3.5.7 源码交付包含 SQL/Hive 支持的可运行发行包，通过调度器测试，再用新安装的 spark-submit 执行独立的小型关系分析应用。

## 官方工作流与派生方式

Spark 3.5.7 source build documentation / Spark 3.5.7 distribution script / Spark DAGSchedulerSuite / Spark developer tools

## 初始环境

- 冻结的官方源码、测试夹具和工具链；依赖事先装载，目标项目构建树和构建产物缓存为空。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 均位于本 session 工作空间；目标版本与 bootstrap 工具分别标识。

## 需要完成的工作

- 核对版本与目标范围，在声明的全量构建基线下实际执行编译/转译及打包。
- 运行冻结的官方测试选择，保存发现、选择、执行、跳过、失败数量及日志。
- 将构建产物安装到独立目录，在源树之外执行 consumer 验证。

## 目标范围

Spark v3.5.7 JVM 分发、SQL/Hive 模块及相关依赖；在 local[2] 模式验收，不将 Spark 外部集群部署混入构建任务。

## 构建与测试入口

### Configure / Generate

- 固定 v3.5.7、Scala 二进制版本、Maven/JDK 组合；reference 启用 -Phive -Phive-thriftserver，不要求 YARN/Kubernetes 服务。

### Build

- ./dev/make-distribution.sh --name thename --tgz -o -Phive -Phive-thriftserver；脚本内部执行 clean package 并延后运行测试。

### Package / Install

- 收集新 dist/ 与生成的 thename tar.gz，安装到 INSTALL_ROOT；Python/R 包不在 reference 范围。

### Official Tests

- ./build/mvn -o -Phive -Phive-thriftserver -Dtest=none -DwildcardSuites=org.apache.spark.scheduler.DAGSchedulerSuite test

## 官方测试选择

- **reference**：org.apache.spark.scheduler.DAGSchedulerSuite，官方 developer-tools 指定的 ScalaTest selector。
- **counts**：跨 reactor 某些模块无匹配可被报告，但 DAGSchedulerSuite 必须实际执行非零测试；禁止把所有模块空选择记为成功。
- **rationale**：覆盖本地 DAG 调度及故障处理；独立 SQL consumer 证明完整分发可工作。

## 独立消费者验收

- 在源树之外通过新发行包 jars 编译一个 Java DataFrame 应用，读取固定小表，执行 join/aggregate，写出后再读回并核对结果。
- 使用 INSTALL_ROOT/bin/spark-submit --master local[2] 提交；锁定本地仓库和 metastore，记录 driver/executor classpath。
- 禁止借用预装 spark-submit 或远端 executor；完整结束并收集真实 job 状态。

## 交付物

- Spark JVM tar.gz、JAR 清单、DAGSchedulerSuite 报告、独立 job JAR 与查询结果。

## 后续使用

要求同一安装包处理一份新增订单分区并复查累计结果；沿用本地数据目录，但不依赖旧输出充当新结果。

## 可选增量变化

- **enabled_by_default**：False
- **variant_kind**：optional_source_delta
- **patch_binding**：null
- **precondition**：保留上一阶段真实构建树；若采用源码修改，先绑定一个有业务语义且有验收的合法补丁及前后版本。
- **acceptance**：重新构建受影响产物，运行相关官方测试与独立 consumer；未绑定补丁时只执行 full-build 基线。
- **not_new_task**：并行度、缓存、clean/no-op/incremental 属于该任务的场景。

## 同一任务的规模配置

### Core：最小完整交付

官方 -pl 子模块构建 core 及其 reactor 依赖并运行 DAGSchedulerSuite；交付 core JAR 和本地 RDD consumer。

### Reference：正式参考配置

完整 JVM SQL/Hive distribution，DAGSchedulerSuite 和独立 SQL 提交。

### Extended：扩展范围

增加官方 -Pconnect 模块或选定 SQL 官方测试套件；测试清单与依赖在采集前冻结，不默认运行所有集群 CI。

## 可控变量

- 固定目标模块、测试套件和工具链；并行编译/测试进程数单独记录。
- 记录构建器与测试子进程 CPU、峰值内存、可写状态、文件/元数据操作及全 session 状态保留。
- 独立区分下载依赖缓存、目标对象/增量缓存和操作系统 page cache；默认目标缓存为空。

## 预期资源形态

- scala_compilation
- multi_module_jvm
- large_dependency_graph
- jar_assembly
- local_job_tests
- workspace_growth

## 后端能力要求

- Linux x86_64 CPU；声明的用户态工具链；可写工作目录、进程与线程支持。
- 普通用户执行；本地 loopback 测试服务允许，默认不需要外部集群、GPU、KVM 或宿主 Docker。

## 离线依赖准备

- 固定官方源码及子模块；预装锁定的构建器/bootstrap 工具和依赖缓存，禁止计时阶段临时升级。
- 冻结测试输入与外部资产；对需要额外平台/Internet 的测试采用预先声明的官方本地范围，不在失败后动态删测试。
- 依赖缓存不得包含能替代本次目标项目构建的旧发布包或已完成目标缓存。
- build/mvn 会按需下载 Maven/Scala；提前装载其精确版本及 Maven 仓库，不依赖第一次计时调用联网。Hadoop/Hive 依赖属于构建闭包但不运行外部服务。

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

- primary_project:https://github.com/apache/spark
- 第三方构建依赖及测试夹具另记 lineage；共享编译器、JVM 或 JS 包不能视为独立工程来源。

## 与已有任务的关系

- 如其他资源组使用此项目，其运行时任务与本卡的源码构建、测试、安装交付目标分别记账。

## 范围说明

- 不把完整跨平台发布 CI 作为默认测试范围；具体平台和选测清单随实例冻结。

## 官方来源

- [E_SPARK_BUILD] [Spark 3.5.7 source build documentation](https://github.com/apache/spark/blob/v3.5.7/docs/building-spark.md) — 检查位置：Apache Maven; Runnable Distribution; Hive/JDBC; submodules
- [E_SPARK_DIST] [Spark 3.5.7 distribution script](https://github.com/apache/spark/blob/v3.5.7/dev/make-distribution.sh) — 检查位置：argument parsing and BUILD_COMMAND clean package
- [E_SPARK_TEST] [Spark DAGSchedulerSuite](https://github.com/apache/spark/blob/v3.5.7/core/src/test/scala/org/apache/spark/scheduler/DAGSchedulerSuite.scala) — 检查位置：DAGSchedulerSuite class and local test fixture
- [E_SPARK_TOOLS] [Spark developer tools](https://spark.apache.org/developer-tools.html) — 检查位置：Running Individual Tests

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
