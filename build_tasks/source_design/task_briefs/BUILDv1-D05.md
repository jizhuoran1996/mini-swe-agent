# BUILDv1-D05 · 构建带 JSON 与 Parquet 的 DuckDB 分析 SDK

Build a DuckDB analytics SDK with JSON and Parquet

**主工程**：[DuckDB](https://github.com/duckdb/duckdb)  
**组别**：数据库与基础设施软件　**规划规模**：大型　**实施优先级**：pilot

**语言**：C++；C；SQL  
**构建系统**：CMake；Ninja；GNU Make wrapper  
**Canonical goal**：`build.install.verify.duckdb`

## Agent 任务目标

交付可离线使用 JSON 和 Parquet 的 DuckDB CLI 与 C API SDK，用外部编译的消费者建立持久化分析库并导出可重新查询的 Parquet。

## 官方工作流与派生方式

DuckDB v1.4.3 CMake core/shell/extensions 与 [capi] 官方单元。

## 初始环境

- 固定版本的完整源代码、声明的子模块和测试数据已预置；目标项目的对象文件、已编译库、测试结果和安装目录为空。
- 编译器、引导工具及第三方依赖来源与版本写入输入清单；依赖缓存和本任务产物缓存分别管理。

## 需要完成的工作

- 使用 v1.4.3 已检查的选项构建核心库、CLI、unit runner 及 json/parquet 扩展。
- 执行官方 [capi] 标签测试，不用后续 main 分支的不同 runner 接口替代。
- 安装 SDK 后在源码外编译消费者，完成 JSON 导入、聚合、持久化与 Parquet 回读。

## 目标范围

DuckDB v1.4.3 core、C API、CLI 与 json/parquet；不运行 HTTPFS、S3 或自动下载扩展。

## 构建与测试入口

### Configure / Generate

- cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DBUILD_SHELL=ON -DBUILD_UNITTESTS=ON -DBUILD_EXTENSIONS="json;parquet"；扩展源码及第三方内容预置。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

- cmake --install "$BUILD_ROOT"；收集安装头文件、共享/静态库、CLI 和实际产物扩展，校验打包清单。

### Official Tests

```bash
"$BUILD_ROOT/test/unittest" "[capi]" --list-test-names-only
```

```bash
"$BUILD_ROOT/test/unittest" "[capi]"
```

## 官方测试选择

- **official_entrypoints**：test/unittest "[capi]"
- **selection**：v1.4.3 源码中实际标记 [capi] 的官方测试，包含基本 API、类型、配置及错误处理。
- **rationale**：验证安装 SDK 的核心语言边界；JSON/Parquet 特性另由新消费者执行验证。

## 独立消费者验收

- 消费者从 INSTALL_ROOT 的 duckdb.h 和库进行 C/C++ 编译，禁止 Python/system DuckDB 代替本轮 native SDK。
- 在新的数据库路径读入固定 JSON、执行连接/聚合、导出 Parquet，并使用独立进程重新打开数据库和 Parquet。
- 检查扩展来自本轮构建或静态链接，禁用网络安装；查询结果与独立期望表一致。

## 交付物

- DuckDB native SDK/CLI 归档与扩展清单
- [capi] 测试枚举及结果
- 消费者源码、数据库和 Parquet 回读报告

## 后续使用

通过同一 SDK 对已有分析库增加一个日期分区，重新导出并检查旧分区不丢失。

## 可选增量变化

- **default**：False
- **kind**：optional_legitimate_patch
- **binding_status**：builder_must_bind_patch_before_collection
- **description**：主任务是干净构建。若增加增量场景，先冻结具有功能意义的上游补丁或已验证配置变更、受影响目标和对应验收；保留同一任务 ID。仅 touch/no-op 不作为独立任务。

## 同一任务的规模配置

### Core：最小完整交付

core/CLI + [capi]，只处理 SQL 表。

### Reference：正式参考配置

core/CLI + json/parquet，独立消费者覆盖格式互操作与持久化。

### Extended：扩展范围

加入来源支持的 icu 扩展及其离线依赖，或扩大官方 SQL 测试范围；新目标清单随实例冻结。

## 可控变量

- 固定实际目标与测试集合；编译并行度和测试并行度独立记录。
- 干净构建为基线；缓存、优化级别和增量模式作为实验场景，不能作为新任务计数。
- 实际资源分类依据参考画像；不预设编译耗时、峰值内存或 syscall 数量。

## 预期资源形态

- C++ analytics engine
- unity build
- extension link
- SDK install
- test binary
- Parquet I/O

## 后端能力要求

- Linux x86_64、普通用户、可写工作目录、真实子进程与文件锁；所需 ABI 和工具链随实例固定。

## 离线依赖准备

- 源代码、子模块、依赖、测试 fixture 与工具链在计时前准备；正式构建禁止隐式访问公网。
- 目标项目由源码重新编译；预置工具/依赖的许可、校验和与来源单列。
- v1.4.3 json/parquet 扩展来源和所需第三方源码与 release 同步，冻结扩展 revision；声明自动安装/自动加载策略。

## 回放与状态

- 后续打包和验收依赖真实编译、链接及测试结束；后台子进程必须纳入本 session 生命周期。
- 保存源码、构建树和安装目录的关系；本轮端口、PID 和临时路径重新绑定。
- 默认按功能和来源验证产物，时间戳、链接 build-id 和归档元数据不要求跨次逐字节一致。

## 最终 oracle

- 核对源版本、构建配置、实际产物路径和功能范围，拒绝系统预装版本或源树导入替代产物。
- 记录官方测试的发现、选择、执行、跳过和失败数量，选择集为空或要求的功能被全部跳过均不通过。
- 在独立消费者目录使用本轮安装包或二进制，检查实际结果和错误处理；消费者验证耗时单独记账。

## 应拒绝的负例

- 用系统预装版本替换本轮产物；只留下日志而无可用安装文件。
- 过滤器未匹配测试或依赖缺失导致全部跳过，却报告成功。
- 测试 [capi] 匹配为空；Parquet 操作靠临时下载扩展完成。

## Builder 实施工作

- 固定源码 revision、工具链和完整依赖快照；实现 source/install/test 产物清单。
- 将官方命令包装为资源可追踪的任务环境，绑定测试集合、端口及真实完成事件。
- 首次真实构建时冻结官方测试的精确数量、消费者期望结果与合理 timeout；不存在实测资源数值。

## 源码血缘

- DuckDB monorepo 与其 json/parquet 扩展合计一个主工程。
- 与 Memory/IO 任务中的 DuckDB/TPC 类运行来源相关，但本题以编译 SDK 交付为目标。

## 与已有任务的关系

与此前资源任务可能共享软件来源；本题交付源码构建与测试后的工程产物，区别于只运行该软件处理数据。

## 范围说明

- 规模标签是规划，实际成本待参考构建画像；本任务不要求外部生产部署或跨宿主集群。
- 文档当前页与 main 分支接口在变化，本卡具体 test 路径和标签以 v1.4.3 已检查源码为准；升级需重新验证。

## 官方来源

- [D_DUCK_BUILD] [DuckDB v1.4.3 build wrapper](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/Makefile) — 检查位置：release rule, BUILD_EXTENSIONS and CMake wrapper
- [D_DUCK_CMAKE] [DuckDB v1.4.3 root CMake build](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/CMakeLists.txt) — 检查位置：BUILD_SHELL, BUILD_UNITTESTS, BUILD_EXTENSIONS and install/export rules
- [D_DUCK_TEST] [DuckDB C API regression tests](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/test/api/capi/test_capi.cpp) — 检查位置：TEST_CASE entries tagged [capi]

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
