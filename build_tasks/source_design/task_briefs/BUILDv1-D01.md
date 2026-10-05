# BUILDv1-D01 · 构建并交付可嵌入应用的 PostgreSQL 工具链

Build and qualify a PostgreSQL server and client SDK

**主工程**：[PostgreSQL](https://git.postgresql.org/git/postgresql.git)  
**组别**：数据库与基础设施软件　**规划规模**：中型　**实施优先级**：pilot

**语言**：C；Perl；SQL  
**构建系统**：Autoconf；GNU Make  
**Canonical goal**：`build.install.verify.postgresql`

## Agent 任务目标

为本地事务分析应用从源码构建 PostgreSQL，交付 server、psql、libpq 与头文件；通过官方回归并证明新应用能够使用这套安装执行事务。

## 官方工作流与派生方式

PostgreSQL 源码安装、core regression 与 isolation suites。

## 初始环境

- 固定版本的完整源代码、声明的子模块和测试数据已预置；目标项目的对象文件、已编译库、测试结果和安装目录为空。
- 编译器、引导工具及第三方依赖来源与版本写入输入清单；依赖缓存和本任务产物缓存分别管理。

## 需要完成的工作

- 在独立构建目录配置私有安装前缀，启用声明的 SSL 与压缩依赖；编译 server/client/interfaces。
- 运行 core regression 和隔离性回归，安装后从消费者目录启动临时数据库并链接 libpq 小程序。
- 交付工具链、功能清单、测试计数与事务结果。

## 目标范围

Linux 原生 server、libpq 与标准客户端工具；reference 启用 OpenSSL/LZ4/Zstandard，不启用 LLVM JIT 或外部认证服务。

## 构建与测试入口

### Configure / Generate

- 从 BUILD_ROOT 执行 "$SRC_ROOT/configure" --prefix="$INSTALL_ROOT" --with-ssl=openssl --with-lz4 --with-zstd；对应头文件/库预置。

### Build

```bash
make -C "$BUILD_ROOT" -j "$BUILD_JOBS" all
```

### Package / Install

- make -C "$BUILD_ROOT" install；归档 INSTALL_ROOT，保留头文件、libpq、server/client 工具及依赖清单。

### Official Tests

```bash
make -C "$BUILD_ROOT" check MAX_CONNECTIONS="$TEST_JOBS"
```

```bash
make -C "$BUILD_ROOT/src/test/isolation" check
```

## 官方测试选择

- **official_entrypoints**：make check；src/test/isolation: make check
- **selection**：完整 core regression schedule + isolation suite；不运行 kerberos/ldap/sepgsql 等外部能力扩展。
- **rationale**：覆盖构建后的 SQL 引擎与并发事务语义，同时保持单 sandbox 内可执行。

## 独立消费者验收

- 使用 INSTALL_ROOT/bin/initdb 和 pg_ctl 在本轮私有数据目录启动普通用户 server，通过本轮 socket/port 连接。
- 消费者单独编译链接 INSTALL_ROOT 中的 libpq，执行建表、批量插入、事务回滚和聚合；检查链接库实际解析路径。
- 停止并重启同一数据目录，用安装的 psql 校验已提交结果仍存在。

## 交付物

- 私有前缀安装归档与依赖/功能 manifest
- core 与 isolation 测试日志、计数和差异文件
- 独立 libpq 消费者源码、二进制及重启查询结果

## 后续使用

交付后新增一批事务记录，用同一安装和数据库完成更新与报表；验证回滚记录未持久化。

## 可选增量变化

- **default**：False
- **kind**：optional_legitimate_patch
- **binding_status**：builder_must_bind_patch_before_collection
- **description**：主任务是干净构建。若增加增量场景，先冻结具有功能意义的上游补丁或已验证配置变更、受影响目标和对应验收；保留同一任务 ID。仅 touch/no-op 不作为独立任务。

## 同一任务的规模配置

### Core：最小完整交付

默认 server、客户端与 libpq；只运行 core regression。

### Reference：正式参考配置

启用 SSL/LZ4/Zstandard，并运行 core 与 isolation 回归。

### Extended：扩展范围

用 make world-bin/install-world-bin 构建 contrib，预置 TAP 依赖并显式配置 --enable-tap-tests，运行 make check-world；范围按所选模块冻结。

## 可控变量

- 固定实际目标与测试集合；编译并行度和测试并行度独立记录。
- 干净构建为基线；缓存、优化级别和增量模式作为实验场景，不能作为新任务计数。
- 实际资源分类依据参考画像；不预设编译耗时、峰值内存或 syscall 数量。

## 预期资源形态

- C compilation
- many translation units
- process creation
- linking
- filesystem metadata
- temporary database I/O
- installed SDK consumer

## 后端能力要求

- Linux x86_64、普通用户、可写工作目录、真实子进程与文件锁；所需 ABI 和工具链随实例固定。
- PostgreSQL 测试和 initdb 必须作为非 root 用户运行；允许本地 socket、共享内存和常规文件同步。

## 离线依赖准备

- 源代码、子模块、依赖、测试 fixture 与工具链在计时前准备；正式构建禁止隐式访问公网。
- 目标项目由源码重新编译；预置工具/依赖的许可、校验和与来源单列。
- 预置 bison/flex、GNU Make、Perl 与所选 readline/ICU/OpenSSL/LZ4/Zstandard 开发依赖，locale 固定。

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
- libpq 消费者实际链接旧系统库；server 未重启就以旧连接返回缓存结果。

## Builder 实施工作

- 固定源码 revision、工具链和完整依赖快照；实现 source/install/test 产物清单。
- 将官方命令包装为资源可追踪的任务环境，绑定测试集合、端口及真实完成事件。
- 首次真实构建时冻结官方测试的精确数量、消费者期望结果与合理 timeout；不存在实测资源数值。

## 源码血缘

- PostgreSQL 一个主项目；contrib 属于同一源码发行版。
- libpq 消费者是验收，不另算工程。

## 与已有任务的关系

与此前资源任务可能共享软件来源；本题交付源码构建与测试后的工程产物，区别于只运行该软件处理数据。

## 范围说明

- 规模标签是规划，实际成本待参考构建画像；本任务不要求外部生产部署或跨宿主集群。

## 官方来源

- [D_PG_BUILD] [PostgreSQL: Building and Installation with Autoconf and Make](https://www.postgresql.org/docs/current/install-make.html) — 检查位置：17.3.2 installation procedure; 17.3.3 prefix, SSL and compression options
- [D_PG_TEST] [PostgreSQL: Running the Tests](https://www.postgresql.org/docs/current/regress-run.html) — 检查位置：31.1.1 make check; 31.1.3 isolation, check-world and TAP; 31.1.4 locale

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
