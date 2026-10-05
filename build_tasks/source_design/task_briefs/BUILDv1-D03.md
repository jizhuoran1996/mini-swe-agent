# BUILDv1-D03 · 构建可持久化的 Redis TLS 安装包

Build a Redis TLS package with persistence validation

**主工程**：[Redis](https://github.com/redis/redis)  
**组别**：数据库与基础设施软件　**规划规模**：小型　**实施优先级**：pilot

**语言**：C；Tcl；Lua  
**构建系统**：GNU Make  
**Canonical goal**：`build.install.verify.redis`

## Agent 任务目标

从固定 Redis 核心源码构建 TLS server 和 CLI，交付可单独运行的安装包，验证数据结构操作和 AOF 重启后的数据一致性。

## 官方工作流与派生方式

Redis 7.2 核心源码构建、TLS 证书脚本与官方 Tcl test runner。

## 初始环境

- 固定版本的完整源代码、声明的子模块和测试数据已预置；目标项目的对象文件、已编译库、测试结果和安装目录为空。
- 编译器、引导工具及第三方依赖来源与版本写入输入清单；依赖缓存和本任务产物缓存分别管理。

## 需要完成的工作

- 从无对象的 7.2 源码树构建 core、CLI 与随源码提供的依赖，启用 TLS。
- 生成本地测试证书，执行明确的 basic/aof 测试单元并保存计数。
- 安装后通过 TLS 写入键、哈希和事务结果，重启并检查持久化。

## 目标范围

Redis 7.2 core server、CLI 和持久化检查工具；明确不声称构建 Redis 8.x 集成查询/JSON/时间序列模块。

## 构建与测试入口

### Configure / Generate

- 该分支使用 Make 变量，无单独 configure；确定 BUILD_TLS=yes 与默认 Linux allocator，OpenSSL/Tcl 依赖已预置。

### Build

```bash
make -C "$SRC_ROOT" -j "$BUILD_JOBS" BUILD_TLS=yes
```

### Package / Install

- make -C "$SRC_ROOT" BUILD_TLS=yes PREFIX="$INSTALL_ROOT" install；归档二进制、声明配置和测试用途证书来源。

### Official Tests

- 在 SRC_ROOT 执行 ./utils/gen-test-certs.sh

- 在 SRC_ROOT 执行 ./runtest --tls --single unit/type/string --single integration/aof --clients "$TEST_JOBS" --baseport "$TEST_BASEPORT" --portcount "$TEST_PORTCOUNT"；预检 --list-tests 必须包含这些单元。

## 官方测试选择

- **official_entrypoints**：./runtest --list-tests；./runtest --tls --single unit/type/string --single integration/aof
- **selection**：官方 string 类型单元与 AOF 集成单元，完整执行各单元现有子测试；TLS 检测与证书预置。
- **rationale**：用相对小的真实编译工程覆盖 allocator/依赖编译、TLS 和 fork/持久化测试。

## 独立消费者验收

- 在消费者私有目录启动 INSTALL_ROOT/bin/redis-server，TLS 仅监听 loopback；所有数据/AOF/日志路径属于本任务。
- 用 INSTALL_ROOT/bin/redis-cli --tls 验证 SET/GET、哈希、MULTI/EXEC 和预期错误；记录实际 server 可执行路径。
- 确认 AOF 提交后优雅关闭，使用同一安装重启并校验数据摘要。

## 交付物

- Redis TLS 私有安装包及固定配置
- 官方 Tcl 单元计数和失败信息
- TLS 消费者操作、AOF 状态与重启一致性结果

## 后续使用

重新打开交付的持久化目录，对已有键进行版本更新并返回重启后的摘要。

## 可选增量变化

- **default**：False
- **kind**：optional_legitimate_patch
- **binding_status**：builder_must_bind_patch_before_collection
- **description**：Redis README 指出依赖或编译选项改变可能需要 make distclean；不得把这种变化自动称作安全增量构建。仅绑定已验证源补丁后开放增量变体。

## 同一任务的规模配置

### Core：最小完整交付

不启用 TLS 的 core build，运行官方 string 单元并验证普通本地客户端。

### Reference：正式参考配置

TLS core build + string/AOF 单元 + TLS 持久化消费者。

### Extended：扩展范围

同一源码构建运行完整普通 Tcl suite 及明确选择的 replication/rdb 单元；扩大测试覆盖而不重复计数。

## 可控变量

- 固定实际目标与测试集合；编译并行度和测试并行度独立记录。
- 干净构建为基线；缓存、优化级别和增量模式作为实验场景，不能作为新任务计数。
- 实际资源分类依据参考画像；不预设编译耗时、峰值内存或 syscall 数量。

## 预期资源形态

- small C build
- bundled allocator build
- Tcl subprocesses
- fork
- TLS
- AOF writes
- persistent files

## 后端能力要求

- Linux x86_64、普通用户、可写工作目录、真实子进程与文件锁；所需 ABI 和工具链随实例固定。
- 支持 fork、loopback、TLS 和文件持久化；测试端口范围由实例独占。

## 离线依赖准备

- 源代码、子模块、依赖、测试 fixture 与工具链在计时前准备；正式构建禁止隐式访问公网。
- 目标项目由源码重新编译；预置工具/依赖的许可、校验和与来源单列。
- 预置 OpenSSL 开发库、Tcl 和 tcl-tls，7.2 源码 deps 完整；无 modules-update/bootstrap 网络阶段。

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

## Builder 实施工作

- 固定源码 revision、工具链和完整依赖快照；实现 source/install/test 产物清单。
- 将官方命令包装为资源可追踪的任务环境，绑定测试集合、端口及真实完成事件。
- 首次真实构建时冻结官方测试的精确数量、消费者期望结果与合理 timeout；不存在实测资源数值。

## 源码血缘

- 固定 Redis 7.2 核心 lineage；与旧 Memory/Network 中 Redis 运行任务共享软件来源。
- jemalloc/Lua/hiredis 是依赖而非新增工程。

## 与已有任务的关系

与此前资源任务可能共享软件来源；本题交付源码构建与测试后的工程产物，区别于只运行该软件处理数据。

## 范围说明

- 规模标签是规划，实际成本待参考构建画像；本任务不要求外部生产部署或跨宿主集群。
- 7.2 是本题明确选择的核心构建来源；若迁移 8.x，需重新锁定模块/许可/工具链并更新同一任务版本。

## 官方来源

- [D_REDIS_BUILD] [Redis 7.2 build and install instructions](https://raw.githubusercontent.com/redis/redis/7.2/README.md) — 检查位置：Building Redis, TLS, dependency cleanup, tests and PREFIX installation
- [D_REDIS_TEST] [Redis test runner selectors](https://raw.githubusercontent.com/redis/redis/7.2/tests/test_helper.tcl) — 检查位置：all_tests, --single, --list-tests, --clients, --baseport, --portcount

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
