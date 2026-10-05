# BUILDv1-B07 · 构建 PHP 并验收 CLI 与 SQLite 数据处理

Build PHP and validate CLI and SQLite processing

**主工程**：[PHP](https://github.com/php/php-src)  
**组别**：编译工具链与语言运行时　**规划规模**：中型　**实施优先级**：pilot

**语言**：C；PHP  
**构建系统**：Autoconf；GNU Make；PHPT  
**Canonical goal**：`php-runtime-source-build`

## Agent 任务目标

从源码构建可安装 PHP runtime，交付 CLI、声明的默认模块及 PDO SQLite 支持，使外部脚本能完成结构化数据入库、查询与结果输出。

## 官方工作流与派生方式

php-src buildconf/configure/make/install and selected PHPT directories

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置 C 工具链、Autoconf、Bison、re2c、pkg-config、libxml2 和 libsqlite3；绑定 PHP revision 及默认 SAPI/扩展配置。

## 需要完成的工作

- 运行 buildconf 并完成默认 PHP 源码构建，显式验收 CLI 与 PDO SQLite。
- 运行语言、JSON、数组和 SQLite 的真实 PHPT 用例。
- 安装到独立前缀，使用源树之外的脚本验证功能与加载配置。

## 目标范围

本机 PHP 默认源码构建、CLI 和 PDO SQLite；若默认构建还产生 CGI 等 SAPI，清单明确记录，不额外部署公网服务。

## 构建与测试入口

### Configure / Generate

- 在 SRC_ROOT 运行 ./buildconf

- 在 SRC_ROOT 运行 ./configure --prefix="$INSTALL_ROOT" --with-pdo-sqlite

### Build

```bash
make -C "$SRC_ROOT" -j"$BUILD_JOBS"
```

### Package / Install

```bash
make -C "$SRC_ROOT" install
```

- 归档安装目录与 php.ini/module 清单；使用本实例声明的配置路径。

### Official Tests

```bash
make -C "$SRC_ROOT" test TESTS="tests/lang ext/json/tests ext/standard/tests/array ext/pdo_sqlite/tests" TEST_PHP_ARGS="-j$TEST_JOBS"
```

- 适配器固定非交互 PHPT 配置，不发送测试结果；解析选定目录及 SKIPIF 结果。

## 官方测试选择

- **reference**：tests/lang、ext/json/tests、ext/standard/tests/array、ext/pdo_sqlite/tests
- **rationale**：覆盖语言执行、结构化输入、集合操作与真实数据库扩展；不选择需要外部数据库的测试。
- **counts**：PHPT 的 PASS/FAIL/XFAIL/SKIP/BORK 必须分类；缺 SQLite 导致整组 skip 不予通过。

## 独立消费者验收

- INSTALL_ROOT/bin/php -n 执行固定消费者或使用仅加载本次声明模块的私有 ini；检查 PHP_BINARY、php --ri 与扩展身份。
- 将 JSON 记录写入新 SQLite 数据库，再启动新的 PHP 进程查询和验证内容。
- 源树和系统 PHP 均不能提供缺失扩展或执行路径。

## 交付物

- php-install.tar.gz
- SAPI、扩展和配置清单
- PHPT 完整摘要与失败日志
- SQLite 消费者工件

## 后续使用

对前一轮数据库执行新查询和合法 schema/data 更新，交付更新结果并用独立进程重新打开验证。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整默认 PHP 构建并提供 CLI
- **tests**：tests/lang 与 ext/json/tests
- **deliverable**：可安装解释器

### Reference：正式参考配置

- **scope**：默认功能加明确 PDO SQLite 合同
- **tests**：四个固定 PHPT 目录
- **deliverable**：可复用数据处理 runtime

### Extended：扩展范围

- **scope**：显式加入 mbstring/OpenSSL 等官方可选扩展和匹配本地依赖
- **tests**：只增加对应扩展的固定本机 PHPT 目录
- **deliverable**：同一 PHP 工程的更丰富模块集

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。

## 预期资源形态

- c_compilation
- parser_generation
- extension_linking
- many_php_processes
- filesystem_metadata
- database_test_io

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。

## 离线依赖准备

- 预装 libxml2/sqlite3 等库，所有扩展依赖均由实例清单固定。
- 不使用 PECL 在线安装或远程数据库；PHPT 只可启动本机进程。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 安装 PHP 的功能模块符合合同。
- 固定 PHPT 集合确实执行；保存所有跳过原因。
- 新进程能读取上轮用新 PHP 写出的 SQLite 数据，结果正确。

## 应拒绝的负例

- 系统 PHP 或全局 php.ini 注入未声明模块。
- PDO SQLite 不存在却靠 skipped tests 获得绿色结果。
- JSON/SQLite 消费者只产生固定输出而未实际处理输入。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- php-src 单项目；SQLite 为预置开发依赖，PHP 不代替其独立工程任务。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。

## 官方来源

- [B_PHP_BUILD] [PHP source README](https://github.com/php/php-src) — 检查位置：Building PHP source code; Testing PHP source code; Installing PHP built from source
- [B_PHP_SQLITE] [PHP PDO SQLite build configuration](https://github.com/php/php-src/blob/master/ext/pdo_sqlite/config.m4) — 检查位置：PDO SQLite option and SQLite dependency checks

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
