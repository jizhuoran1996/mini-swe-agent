# 60 个工程构建与测试 Agent 任务

版本：`sandbox_build_60_source_based_v1`  
用途：为 THENAME 补充不同规模的真实工程构建与测试轨迹。  
来源核查：2026-10-05。

## 一、这组任务怎么构造

本包选取 60 个具体工程，分六组，每组十题。默认任务是从源码完整构建声明的工程目标、运行有意义的官方测试，再向独立消费者交付可用的库、工具、运行时、服务程序或软件包。规模从 zlib 等基础库延伸到 PyTorch、TensorFlow、LLVM/Clang、Rust、Envoy 等大型工程。

完整构建是主场景，增量构建是同一任务的可选配置。每题都包含官方构建/测试入口、初始状态、交付要求、独立验收、规模配置、资源控制与后续使用方式。不会把改变 jobs、开关、cache 或重复运行当成额外任务数量。

这是一份来源已核查的任务设计与实现交接包：包含 60 张任务卡和 60 份提示模板，尚未在目标 sandbox 上完成工程构建与轨迹采集；实际资源测量字段保留为空。源码、依赖和巨型编译产物不随包分发。

## 二、六组覆盖

| 组 | 内容 | 数量 | 主要工程行为 |
|---|---|---:|---|
| A | 原生基础库与命令行工具 | 10 | 配置探测、短编译动作、静态/共享库与基础测试 |
| B | 编译工具链与语言运行时 | 10 | bootstrap、代码生成、大型链接与工具链测试 |
| C | 多媒体、图形与地理计算工程 | 10 | 模块/插件组合、原生依赖、资产与无头测试 |
| D | 数据库与基础设施软件 | 10 | 本地服务测试、进程/文件活动和临时状态 |
| E | JVM 与 JavaScript 工程 | 10 | 依赖图、代码生成、包交付与运行时测试 |
| F | 机器学习与数值计算框架 | 10 | 混合语言 native 编译、框架链接与 wheel/库交付 |

这些分组用于组织来源生态，不是六个互斥资源 class。一个 PyTorch 或数据库构建可以同时表现出较高 CPU 工作量、链接阶段内存峰值、大量小文件操作和显著 build-tree 占用。正式分类仍依据固定参考配置上的实际画像。

## 三、为什么适合 cloud sandbox

工程构建把几类系统行为放在有实际交付目标的完整 session 内：configure 和代码生成会启动工具并探测环境；编译产生并行子进程和中间文件；链接与打包改变 CPU、内存和工作空间形态；测试运行新的程序、线程和临时服务；产物与构建状态可以跨 agent 调用保留。

因此，这组任务适合比较 native/container/VM 的实际执行成本，也适合在相同轨迹集合上改变 CPU 配额、内存限制、准入并发和状态保留策略。尤其是 process/metadata 覆盖，不能只看一个 syscall 总数：任务画像应区分进程创建/等待、文件路径检查、目录遍历、mmap/fault、同步和 socket 操作族。

工作空间与 I/O 分开记录。大量对象文件和安装包会增加状态保存规模，但不必然意味着持续 block-device I/O；下载依赖与镜像准备产生的流量也不能混作工具编译本身的访问量。

## 四、构建规模与 PyTorch

每题提供 core、reference、extended 三档。同一工程可通过真实组件、工具链阶段、设备编译后端和正式测试范围扩展工作量。参考档仍可为小工程：保留自然的小型工作负载，才便于判断 sandbox 在短任务和大任务上的差别。

PyTorch 是 `BUILDv1-F01`。其默认目标是 CPU 源码构建、wheel 交付、官方 CPU 测试，以及在源码目录之外的新环境安装该 wheel 后完成张量/模型功能验收。CUDA SDK 编译可作为扩展，但不把 GPU runtime 测试加入所有后端的默认门槛。这一任务测工程构建，与上一组使用 PyTorch 做 GPU 计算的任务不同。

当前规划规模分布：小型 3 题、中型 24 题、大型 20 题、超大型 13 题。这些是工程选型标签，正式运行时长、CPU、内存和磁盘额度由参考画像确定。

## 五、默认场景和验收

默认初始状态含固定源码、工具链与预置依赖，不含目标工程的构建输出或对象缓存。完整构建、工程测试与交付物消费都真实执行；仅 agent 决策 LLM 的响应和等待被轨迹回放替代。

验收包含三部分：核对产物来自本次源码构建；确认冻结的官方测试集合非空并实际执行；从源码树之外消费产物完成有意义的功能检查。例如，编译 C consumer 并链接新库，安装新 wheel 后调用 native 算子，用新构建的数据库执行带结果校验的查询。

增量场景从已验证的构建树出发，应用绑定的特性变化或真实补丁并重新验收。no-op rebuild 仅作为元数据/构建图诊断。依赖下载缓存、构建树、编译/action cache、页缓存和 sandbox snapshot 分别声明，以免缓存差异掩盖受测工作量。

## 六、60 题目录

### A · 原生基础库与命令行工具

| ID | 工程任务 | 规划规模 |
|---|---|---|
| BUILDv1-A01 | 构建并交付 zlib 压缩开发包 | 小型 |
| BUILDv1-A02 | 构建 Zstandard 工具与可嵌入压缩库 | 中型 |
| BUILDv1-A03 | 构建多格式归档工具和开发包 | 中型 |
| BUILDv1-A04 | 构建并验证 HTTPS 客户端开发包 | 中型 |
| BUILDv1-A05 | 构建密码与 TLS 软件开发包 | 中型 |
| BUILDv1-A06 | 构建异步 I/O 与进程管理开发包 | 中型 |
| BUILDv1-A07 | 构建带 TLS 支持的事件驱动库 | 中型 |
| BUILDv1-A08 | 构建多编码正则与 JIT 开发包 | 中型 |
| BUILDv1-A09 | 构建 HTTP/2 开发包与本地工具链 | 中型 |
| BUILDv1-A10 | 构建可嵌入 Git 工作区管理开发包 | 中型 |

### B · 编译工具链与语言运行时

| ID | 工程任务 | 规划规模 |
|---|---|---|
| BUILDv1-B01 | 构建并交付 LLVM/Clang 本机 C/C++ 工具链 | 超大型 |
| BUILDv1-B02 | 自举构建 GCC C/C++ 编译器与运行库 | 超大型 |
| BUILDv1-B03 | 构建并验收 ELF 汇编、链接与归档工具 | 中型 |
| BUILDv1-B04 | 构建含数据库与并发支持的 CPython 发行目录 | 中型 |
| BUILDv1-B05 | 构建 Node.js 并交付本地事件与国际化运行环境 | 大型 |
| BUILDv1-B06 | 构建并安装 Ruby 解释器与标准扩展 | 中型 |
| BUILDv1-B07 | 构建 PHP 并验收 CLI 与 SQLite 数据处理 | 中型 |
| BUILDv1-B08 | 从源码构建 Go 工具链并交付本机开发环境 | 大型 |
| BUILDv1-B09 | 自举 Rust 编译器、标准库与文档工具 | 超大型 |
| BUILDv1-B10 | 构建 OpenJDK 镜像并验收编译器与 JVM | 大型 |

### C · 多媒体、图形与地理计算工程

| ID | 工程任务 | 规划规模 |
|---|---|---|
| BUILDv1-C01 | 构建可安装的 CPU 媒体工具链并通过 FATE | 大型 |
| BUILDv1-C02 | 构建插件化媒体 SDK 与离线音视频管线 | 大型 |
| BUILDv1-C03 | 交付可开发和可测试的图像处理安装包 | 中型 |
| BUILDv1-C04 | 构建流式图像处理 C/C++ SDK | 中型 |
| BUILDv1-C05 | 构建可复用的 CPU 视觉开发工具包 | 大型 |
| BUILDv1-C06 | 构建无界面的 Blender 场景处理与 CPU 渲染发行包 | 超大型 |
| BUILDv1-C07 | 构建 Godot 编辑器与 Linux 导出模板 | 大型 |
| BUILDv1-C08 | 构建 CPU 软件图形栈并验证离屏执行 | 大型 |
| BUILDv1-C09 | 构建栅格与矢量数据开发发行包 | 大型 |
| BUILDv1-C10 | 构建支持 CPU 离屏可视化的科学 SDK | 超大型 |

### D · 数据库与基础设施软件

| ID | 工程任务 | 规划规模 |
|---|---|---|
| BUILDv1-D01 | 构建并交付可嵌入应用的 PostgreSQL 工具链 | 中型 |
| BUILDv1-D02 | 构建并验证 MariaDB 事务数据库发行包 | 大型 |
| BUILDv1-D03 | 构建可持久化的 Redis TLS 安装包 | 小型 |
| BUILDv1-D04 | 交付经验证的 RocksDB 嵌入式存储 SDK | 大型 |
| BUILDv1-D05 | 构建带 JSON 与 Parquet 的 DuckDB 分析 SDK | 大型 |
| BUILDv1-D06 | 构建可独立链接的 Arrow 列式数据 SDK | 大型 |
| BUILDv1-D07 | 构建并验证完整 ClickHouse 分析工具包 | 超大型 |
| BUILDv1-D08 | 构建可持久化的 etcd 发布工具包 | 中型 |
| BUILDv1-D09 | 构建并交付支持 TLS 的 NGINX 代理包 | 中型 |
| BUILDv1-D10 | 构建并验证 Envoy 代理发行二进制 | 超大型 |

### E · JVM 与 JavaScript 工程

| ID | 工程任务 | 规划规模 |
|---|---|---|
| BUILDv1-E01 | 构建 Kafka 发行包并验收事件往返 | 大型 |
| BUILDv1-E02 | 构建 Spark SQL 发行包并交付本地分析程序 | 超大型 |
| BUILDv1-E03 | 构建 Flink 发行包并验收本地流处理 | 超大型 |
| BUILDv1-E04 | 构建 Lucene 库并交付可重载索引示例 | 大型 |
| BUILDv1-E05 | 构建本机 Elasticsearch 分发并验收查询 | 超大型 |
| BUILDv1-E06 | 构建 TypeScript 编译器包并验收类型检查 | 中型 |
| BUILDv1-E07 | 构建 Rollup 的 JS 与原生解析器分发 | 大型 |
| BUILDv1-E08 | 构建 Babel 工具链并验收跨版本转译 | 中型 |
| BUILDv1-E09 | 构建 esbuild 本机工具并验收打包接口 | 小型 |
| BUILDv1-E10 | 构建 SWC 原生 Node 扩展并验收转译 | 大型 |

### F · 机器学习与数值计算框架

| ID | 工程任务 | 规划规模 |
|---|---|---|
| BUILDv1-F01 | 构建并交付 CPU PyTorch 发行包及扩展开发环境 | 超大型 |
| BUILDv1-F02 | 从源码交付 TensorFlow CPU wheel 与可重载模型支持 | 超大型 |
| BUILDv1-F03 | 编译 JAX 的 CPU jaxlib/XLA 并交付配套 wheel | 超大型 |
| BUILDv1-F04 | 构建 scikit-learn 原生扩展发行包并验证邻域搜索与模型流水线 | 中型 |
| BUILDv1-F05 | 编译 NumPy 数组运行时及开发接口发行包 | 中型 |
| BUILDv1-F06 | 构建 SciPy 多语言数值 wheel 并验证线性代数与优化 | 大型 |
| BUILDv1-F07 | 构建 pandas Cython 发行包并验收分组与时间索引 | 中型 |
| BUILDv1-F08 | 构建 XGBoost 原生核心与 Python 发行包 | 大型 |
| BUILDv1-F09 | 构建 LightGBM CPU 命令行与原生 SDK | 中型 |
| BUILDv1-F10 | 构建 ONNX Runtime CPU wheel 与原生运行库 | 大型 |

## 七、文件怎么用

| 路径 | 用途 |
|---|---|
| `TASK_CATALOG.md` | 六组任务总览，链接到完整任务卡 |
| `task_briefs/` | 60 张任务卡，含具体构建/测试入口、规模与验收 |
| `agent_prompts/` | 60 份初始任务与可选后续请求模板 |
| `task_registry.json`、`tasks.jsonl` | 同一批完整机器可读任务记录 |
| `sources.json`、`SOURCES.md` | 官方页面/源码检查位置及版本信息 |
| `templates/` | source/dependency lock、实例、测试、回放和运行结果模板 |
| `BUILD_SCENARIOS.md` | clean、cache、incremental 和 no-op 的可比较场景 |
| `SOURCE_AND_DEPENDENCIES.md` | 版本、工具链、离线依赖和输入/产物边界 |
| `TEST_AND_ORACLE.md` | 测试集合、独立 consumer 和失败分类 |
| `MEASUREMENT.md` | 阶段、CPU/内存、workspace、I/O 与 OS 交互口径 |
| `REPLAY_AND_STATE.md` | 真实构建回放、后台作业和跨轮状态 |
| `BACKEND_CAPABILITIES.md` | Linux/CPU 默认范围与显式扩展能力 |
| `SIZE_AND_PILOTS.md` | 三档规模与推荐首批 12 题 |
| `DEDUP_AND_SCOPE.md` | 主工程计数、依赖血缘与已有任务的关系 |
| `CODEX_HANDOFF.md` | 从设计到可运行实例、轨迹及资源画像的实施步骤 |
| `scripts/` | 结构校验、视图重建和发布校验和脚本 |
| `VALIDATION_REPORT.json` | 本版结构与一致性校验结果 |
| `CHECKSUMS.sha256` | 发布包内文件的 SHA-256 |

在解压后的包根目录运行：

```bash
python3 scripts/validate_pack.py --self-check
```

修改 registry 后运行 `python3 scripts/render_views.py --root .`，再执行结构校验。实现新阶段后保存证据与 hash，更新 readiness；结构校验检查记录一致性，工程成功由任务专用 oracle 判定。

## 八、下一步怎么实施

建议每组先做两题，完成依赖预置、真实构建、独立验收、轨迹回放与统一资源记账：zlib/libgit2、CPython/binutils、FFmpeg/libvips、DuckDB/etcd、TypeScript/esbuild、NumPy/XGBoost。随后推进 PyTorch 等大型工程，而不是一次准备所有超大依赖环境。

这组任务侧重构建。数据库与服务程序会有本地功能消费者，但“sandbox 内部署服务—修改—从外部验收”的入口、长驻服务和跨轮管理问题仍适合下一组独立任务。

本版共 60 个主工程任务、196 条官方来源记录（196 个不同 URL）。完整来源与逐题绑定关系保存在包内。
