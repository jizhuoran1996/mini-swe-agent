# BUILDv1-B05 · 构建 Node.js 并交付本地事件与国际化运行环境

Build Node.js with local event processing and internationalization

**主工程**：[Node.js](https://github.com/nodejs/node)  
**组别**：编译工具链与语言运行时　**规划规模**：大型　**实施优先级**：standard

**语言**：C++；C；JavaScript；Python  
**构建系统**：configure.py；GYP；GNU Make；Node test.py  
**Canonical goal**：`nodejs-runtime-source-build`

## Agent 任务目标

从源码构建含 V8、核心原生库与 full ICU 的 Node.js，交付可用于文件处理、worker/子进程和本地请求处理的运行环境，并验证非英语国际化功能。

## 官方工作流与派生方式

Node configure/make/install, tools/test.py subsystem selectors, local ICU build

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置匹配 revision 的 C++ 编译器、Python、Make，以及本地锁定 ICU 源码；V8/OpenSSL/libuv 等随源树的依赖不得替换为目标 Node 预编译包。

## 需要完成的工作

- 配置固定国际化范围并真实编译整个 Node.js runtime。
- 运行官方 streams、child-process 和 message 相关本地测试。
- 安装后在新目录执行 Intl、worker 和本地服务消费者，记录实际执行路径。

## 目标范围

Linux x86_64 Node/V8 与 full ICU、bundled 原生依赖；声明的 Node 版本不得由 PATH 自动决定。

## 构建与测试入口

### Configure / Generate

- 在 SRC_ROOT 执行 ./configure --prefix="$INSTALL_ROOT" --with-intl=full-icu --with-icu-source="$DEPS_ROOT/icu"

- Temporal 支持必须显式固定：支持对应选项的 revision 基线使用 --v8-disable-temporal-support；扩展 profile 才启用已锁定 Rust 依赖。

### Build

```bash
make -C "$SRC_ROOT" -j"$BUILD_JOBS"
```

### Package / Install

```bash
make -C "$SRC_ROOT" install
```

- 归档完整安装树；不以预装 node/npm 替代编译产物。

### Official Tests

- 在 SRC_ROOT 运行 python3 tools/test.py "test/parallel/test-stream-*"

- 在 SRC_ROOT 运行 python3 tools/test.py child-process

- 在 SRC_ROOT 运行 python3 tools/test.py test/message

## 官方测试选择

- **reference**：test/parallel/test-stream-*、child-process 子系统、test/message
- **rationale**：直接覆盖 stream、fork/exec 和错误输出，适合普通 sandbox 内执行；本地 socket/pipe 为允许能力。
- **counts**：解析 test.py 实际选择和结果；预先固定并行度及平台排除，不以测试失败后重新过滤。

## 独立消费者验收

- INSTALL_ROOT/bin/node 执行源树外消费者；断言 process.execPath 和 process.versions。
- 验证至少两个非英语 locale 的固定格式结果；通过 worker_threads 和子进程处理确定性输入。
- 通过本轮动态 loopback 端口发起一次请求，收到预期内容后关闭服务；无外部网站依赖。

## 交付物

- node-runtime.tar.gz
- configure/ICU/Temporal 功能清单
- 官方测试报告
- 消费者结果及本地服务退出记录

## 后续使用

使用同一安装 runtime 运行新请求的 JS 应用，生成报告并通过另一个外部于该进程的本地客户端验收。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：Node + small-icu，固定本地 ICU
- **tests**：streams 与 message
- **deliverable**：可使用的 Node runtime

### Reference：正式参考配置

- **scope**：Node + full ICU，无隐式 Temporal Rust 自动检测
- **tests**：streams/child-process/message
- **deliverable**：包含声明 locale 支持的完整安装树

### Extended：扩展范围

- **scope**：若锁定版本支持，则启用 Temporal，加入对应 vendored Rust/Cargo 依赖
- **tests**：make test-only 的冻结本机集合及 Temporal 功能验收
- **deliverable**：同一 Node 的更多原生能力

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。
- Intl、Temporal、bundled/system 依赖选择固定；测试 worker 数不能随机器自行变化。

## 预期资源形态

- large_cpp_build
- v8_generated_code
- linker_memory
- many_processes
- local_sockets
- metadata_and_install_io

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。
- 允许 loopback socket、pipe、线程和子进程；不需要公开入站端口。

## 离线依赖准备

- ICU 使用本地源码/归档路径，禁止 configure 下载 URL。
- 如启用 Temporal，预置与源树对应的 Cargo vendor/registry 数据；默认 profile 显式固定关闭，防止安装 Rust 后自动改变范围。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 新 Node 的功能/版本与 full ICU 合同一致。
- 官方选定测试非空且消费者由新 runtime 完成。

## 应拒绝的负例

- 用系统 Node 跑测试或消费程序。
- ICU 构建回退为英语小数据却声称 full ICU。
- 后台服务未真正 ready 或未释放子进程。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- Node monorepo 包含 V8/libuv/OpenSSL 等依赖；这些共享依赖与其他组对应工程记录关联。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。

## 官方来源

- [B_NODE_BUILD] [Building Node.js](https://github.com/nodejs/node/blob/main/BUILDING.md) — 检查位置：Unix build/install/test; ICU options; Temporal support
- [B_NODE_CONFIG] [Node.js configure.py](https://github.com/nodejs/node/blob/main/configure.py) — 检查位置：--prefix and Intl/Temporal configuration parser

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
