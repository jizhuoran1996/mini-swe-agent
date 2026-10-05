# BUILDv1-D04 · 交付经验证的 RocksDB 嵌入式存储 SDK

Build and validate a RocksDB embedded storage SDK

**主工程**：[RocksDB](https://github.com/facebook/rocksdb)  
**组别**：数据库与基础设施软件　**规划规模**：大型　**实施优先级**：standard

**语言**：C++；C  
**构建系统**：GNU Make  
**Canonical goal**：`build.install.verify.rocksdb`

## Agent 任务目标

构建并打包可供独立应用链接的 RocksDB SDK，使新的小型存储程序能够批量写入、读取和重启数据库，并提供官方测试证据。

## 官方工作流与派生方式

RocksDB static/shared library Make targets 与 db_basic_test/table_test。

## 初始环境

- 固定版本的完整源代码、声明的子模块和测试数据已预置；目标项目的对象文件、已编译库、测试结果和安装目录为空。
- 编译器、引导工具及第三方依赖来源与版本写入输入清单；依赖缓存和本任务产物缓存分别管理。

## 需要完成的工作

- 锁定编译器和压缩依赖，编译 static/shared library 与所选测试二进制。
- 运行 db_basic_test 和 table_test 全部已发现案例，临时数据库落入 sandbox 工作盘。
- 安装头文件和库，在源码外编译消费者并验证批量更新和重新打开。

## 目标范围

RocksDB C++ shared/static SDK、头文件和两个官方测试可执行；不包含 Java/JNI、远程存储或长期 db_bench 性能运行。

## 构建与测试入口

### Configure / Generate

- 参考 profile 显式固定 DEBUG_LEVEL=0、编译器和压缩依赖；同一构建树内的库、测试及安装命令使用相同变量，不混用 release/debug 对象。

### Build

```bash
make -C "$SRC_ROOT" -j "$BUILD_JOBS" DEBUG_LEVEL=0 static_lib shared_lib db_basic_test table_test
```

### Package / Install

- make -C "$SRC_ROOT" DEBUG_LEVEL=0 PREFIX="$INSTALL_ROOT" install-static install-shared；保留 pkg-config 元数据和运行时库链接。

### Official Tests

- 在 SRC_ROOT 执行 TEST_TMPDIR="$TEST_TMPDIR" ./db_basic_test --gtest_list_tests

- 在 SRC_ROOT 执行 TEST_TMPDIR="$TEST_TMPDIR" ./table_test --gtest_list_tests

- 在 SRC_ROOT 执行 TEST_TMPDIR="$TEST_TMPDIR" ./db_basic_test

- 在 SRC_ROOT 执行 TEST_TMPDIR="$TEST_TMPDIR" ./table_test

## 官方测试选择

- **official_entrypoints**：db_basic_test；table_test
- **selection**：两个完整官方 gtest 二进制中的非禁用测试；保存运行前枚举与实际执行结果。
- **rationale**：覆盖库构建后打开/读写及表格式行为，目标列表明确并与 SDK 用途一致。

## 独立消费者验收

- 新的 C++ 源文件只通过 INSTALL_ROOT 头文件和库编译，检查共享对象实际来源。
- 执行 WriteBatch、读取和迭代；关闭后新进程重新打开数据库，校验键值及删除状态。
- 交付静态与动态链接消费者的构建指令；静态链接模式明确额外系统依赖。

## 交付物

- RocksDB SDK 归档、pkg-config 和依赖清单
- db_basic_test/table_test 报告
- 消费者源码、独立构建日志及重开数据库结果

## 后续使用

用已交付 SDK 新增第二个消费者操作，更新既有键范围并确认原始持久化数据的兼容性。

## 可选增量变化

- **default**：False
- **kind**：optional_legitimate_patch
- **binding_status**：builder_must_bind_patch_before_collection
- **description**：主任务是干净构建。若增加增量场景，先冻结具有功能意义的上游补丁或已验证配置变更、受影响目标和对应验收；保留同一任务 ID。仅 touch/no-op 不作为独立任务。

## 同一任务的规模配置

### Core：最小完整交付

static_lib + db_basic_test 与静态消费者。

### Reference：正式参考配置

static/shared 两种库 + db_basic_test/table_test，提供可重开的嵌入式数据库。

### Extended：扩展范围

添加来源 Makefile 中实际声明的官方数据库/事务测试目标，按枚举清单固定；Java/JNI 若引入则另声明工具链，仍不新增任务 ID。

## 可控变量

- 固定实际目标与测试集合；编译并行度和测试并行度独立记录。
- 干净构建为基线；缓存、优化级别和增量模式作为实验场景，不能作为新任务计数。
- 实际资源分类依据参考画像；不预设编译耗时、峰值内存或 syscall 数量。

## 预期资源形态

- large C++ library
- template compilation
- static and shared linking
- gtest process
- LSM test I/O
- consumer link

## 后端能力要求

- Linux x86_64、普通用户、可写工作目录、真实子进程与文件锁；所需 ABI 和工具链随实例固定。

## 离线依赖准备

- 源代码、子模块、依赖、测试 fixture 与工具链在计时前准备；正式构建禁止隐式访问公网。
- 目标项目由源码重新编译；预置工具/依赖的许可、校验和与来源单列。
- 所选 Snappy/Zlib/Bzip2/LZ4/Zstd/gflags 与测试依赖全部预置并冻结发现结果；TEST_TMPDIR 必须位于本任务计量盘而不是意外 /dev/shm。

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
- 只有 static 库但报告两种库齐备；消费者实际链接系统 librocksdb。

## Builder 实施工作

- 固定源码 revision、工具链和完整依赖快照；实现 source/install/test 产物清单。
- 将官方命令包装为资源可追踪的任务环境，绑定测试集合、端口及真实完成事件。
- 首次真实构建时冻结官方测试的精确数量、消费者期望结果与合理 timeout；不存在实测资源数值。

## 源码血缘

- 同一 RocksDB 项目的两种库形态属于一个任务。
- 与旧 I/O/Memory 的 RocksDB 运行工作负载共享引擎，实现目标不同。

## 与已有任务的关系

与此前资源任务可能共享软件来源；本题交付源码构建与测试后的工程产物，区别于只运行该软件处理数据。

## 范围说明

- 规模标签是规划，实际成本待参考构建画像；本任务不要求外部生产部署或跨宿主集群。

## 官方来源

- [D_ROCKS_BUILD] [RocksDB Makefile](https://raw.githubusercontent.com/facebook/rocksdb/main/Makefile) — 检查位置：static_lib, shared_lib, db_basic_test, table_test, install-static/install-shared, PREFIX
- [D_ROCKS_TEST] [RocksDB Contribution Guide](https://github.com/facebook/rocksdb/wiki/RocksDB-Contribution-Guide) — 检查位置：Running individual tests, gtest_filter and TEST_TMPDIR

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
