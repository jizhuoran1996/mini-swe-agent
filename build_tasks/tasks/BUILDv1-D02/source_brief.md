# BUILDv1-D02 · 构建并验证 MariaDB 事务数据库发行包

Build and qualify a MariaDB transactional database package

**主工程**：[MariaDB](https://github.com/MariaDB/server)  
**组别**：数据库与基础设施软件　**规划规模**：大型　**实施优先级**：standard

**语言**：C；C++；Perl；SQL  
**构建系统**：CMake；Ninja；MTR  
**Canonical goal**：`build.install.verify.mariadb`

## Agent 任务目标

交付一套包含事务存储引擎和客户端的 MariaDB 私有安装，使用官方测试及新建业务数据库验证 SQL 行为，并能恢复交付的备份。

## 官方工作流与派生方式

MariaDB 11.8 源码 CMake 构建、unit tests 与 MTR main.insert/main.select。

## 初始环境

- 固定版本的完整源代码、声明的子模块和测试数据已预置；目标项目的对象文件、已编译库、测试结果和安装目录为空。
- 编译器、引导工具及第三方依赖来源与版本写入输入清单；依赖缓存和本任务产物缓存分别管理。

## 需要完成的工作

- 锁定 11.8 分支的具体 revision、子模块和依赖；在空构建目录生成 server/client/unit-test 目标。
- 执行 CTest 单元测试及两个完整 MTR SQL 文件，随后安装到私有前缀。
- 用本轮数据库工具创建、导出和恢复一个小型订单库，检查事务与查询结果。

## 目标范围

MariaDB server、SQL 客户端、备份/初始化工具和配置声明的默认本地引擎；不部署 Galera 或外部 ColumnStore。

## 构建与测试入口

### Configure / Generate

- cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DWITH_UNIT_TESTS=ON；冻结所选引擎及插件清单。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

- cmake --install "$BUILD_ROOT"；打包私有前缀、默认模板与所需插件。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" --output-on-failure
```

- 在 BUILD_ROOT 执行 mysql-test/mtr --parallel="$TEST_JOBS" main.insert main.select；数据落在声明的可写盘，reference 不加 --mem。

## 官方测试选择

- **official_entrypoints**：CTest registered unit tests；mysql-test/mtr main.insert main.select
- **selection**：完整内建 unit selection，加 main.insert 与 main.select 两个实际 SQL 回归文件及其官方 include。
- **rationale**：同时覆盖 C/C++ 库逻辑与真实 server 执行 SQL；不靠全套分布式测试制造环境要求。

## 独立消费者验收

- 在 INSTALL_ROOT 中解析 mariadbd、mariadb-install-db、mariadb 及导出工具，初始化私有 datadir 并以当前用户启动。
- 以安装客户端执行订单/明细表事务、约束失败、回滚及连接聚合；查询引擎列表确认所需事务引擎存在。
- 导出后恢复至第二个私有 datadir；重新连接校验行数、主键集合和聚合。

## 交付物

- 私有 MariaDB 安装归档与启用引擎清单
- CTest/MTR 测试报告、SQL 差异和运行计数
- 订单库导出文件及独立恢复验收报告

## 后续使用

在恢复后的库上追加订单与索引，用相同安装生成新的聚合结果并校验原数据保留。

## 可选增量变化

- **default**：False
- **kind**：optional_legitimate_patch
- **binding_status**：builder_must_bind_patch_before_collection
- **description**：主任务是干净构建。若增加增量场景，先冻结具有功能意义的上游补丁或已验证配置变更、受影响目标和对应验收；保留同一任务 ID。仅 touch/no-op 不作为独立任务。

## 同一任务的规模配置

### Core：最小完整交付

完整默认 server/client + CTest；消费者只做本地事务。

### Reference：正式参考配置

在 core 上运行 main.insert/main.select，并交付可恢复的应用数据库。

### Extended：扩展范围

保留同一工程，扩展到声明的 main suite 和所选引擎官方测试目录；运行前冻结实际 suite 列表与跳过条件。

## 可控变量

- 固定实际目标与测试集合；编译并行度和测试并行度独立记录。
- 干净构建为基线；缓存、优化级别和增量模式作为实验场景，不能作为新任务计数。
- 实际资源分类依据参考画像；不预设编译耗时、峰值内存或 syscall 数量。

## 预期资源形态

- large C++ compile graph
- link memory
- plugins
- process-heavy tests
- database temp files
- install tree

## 后端能力要求

- Linux x86_64、普通用户、可写工作目录、真实子进程与文件锁；所需 ABI 和工具链随实例固定。
- 本地 Unix socket/loopback、普通用户数据库进程；MTR 的临时 datadir 和端口必须隔离。

## 离线依赖准备

- 源代码、子模块、依赖、测试 fixture 与工具链在计时前准备；正式构建禁止隐式访问公网。
- 目标项目由源码重新编译；预置工具/依赖的许可、校验和与来源单列。
- 预置 CMake/Ninja、编译器、Perl、bison、压缩/TLS/终端依赖及完整子模块；禁止构建时自动 clone 缺失组件。

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
- 仅构建客户端或关闭所需存储引擎；MTR 误连另一个 server。

## Builder 实施工作

- 固定源码 revision、工具链和完整依赖快照；实现 source/install/test 产物清单。
- 将官方命令包装为资源可追踪的任务环境，绑定测试集合、端口及真实完成事件。
- 首次真实构建时冻结官方测试的精确数量、消费者期望结果与合理 timeout；不存在实测资源数值。

## 源码血缘

- MariaDB 与 MySQL 有历史源码关系，本包仅将 MariaDB 算为该任务的主工程。
- 官方 MTR 和 Connector/C 子模块归入 MariaDB 构建，不单独计数。

## 与已有任务的关系

与此前资源任务可能共享软件来源；本题交付源码构建与测试后的工程产物，区别于只运行该软件处理数据。

## 范围说明

- 规模标签是规划，实际成本待参考构建画像；本任务不要求外部生产部署或跨宿主集群。
- MTR --mem 会把测试存储压力改为内存压力，应作为独立场景；参考配置不使用该选项。

## 官方来源

- [D_MARIA_BUILD] [Get the code, build it, test it](https://mariadb.org/get-involved/getting-started-for-developers/get-code-build-test/) — 检查位置：Compile; Testing the server; Starting mariadbd after build
- [D_MARIA_CMAKE] [MariaDB 11.8 CMake build configuration](https://raw.githubusercontent.com/MariaDB/server/11.8/CMakeLists.txt) — 检查位置：WITH_UNIT_TESTS; ENABLE_TESTING; bundled client library build
- [D_MARIA_INSERT] [MariaDB insert regression fixture](https://raw.githubusercontent.com/MariaDB/server/11.8/mysql-test/main/insert.test) — 检查位置：main.insert SQL regression, inserts, defaults, keys and old-value references
- [D_MARIA_SELECT] [MariaDB select regression fixture](https://raw.githubusercontent.com/MariaDB/server/11.8/mysql-test/main/select.test) — 检查位置：main.select SQL regression and required include files

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
