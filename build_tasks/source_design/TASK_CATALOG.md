# 60 个工程构建与测试任务

每个 ID 代表一个主工程交付目标。规模为规划标签；完整命令、测试选择和可选配置见任务卡。

## A · 原生基础库与命令行工具

配置探测、短编译动作、静态/共享库与基础测试。

| ID | 主工程与交付 | 构建系统 | 规划规模 |
|---|---|---|---|
| [BUILDv1-A01](task_briefs/BUILDv1-A01.md) | 构建并交付 zlib 压缩开发包 | configure；GNU Make | 小型 |
| [BUILDv1-A02](task_briefs/BUILDv1-A02.md) | 构建 Zstandard 工具与可嵌入压缩库 | GNU Make | 中型 |
| [BUILDv1-A03](task_briefs/BUILDv1-A03.md) | 构建多格式归档工具和开发包 | CMake；Make or Ninja | 中型 |
| [BUILDv1-A04](task_briefs/BUILDv1-A04.md) | 构建并验证 HTTPS 客户端开发包 | CMake；Make or Ninja | 中型 |
| [BUILDv1-A05](task_briefs/BUILDv1-A05.md) | 构建密码与 TLS 软件开发包 | Configure；GNU Make | 中型 |
| [BUILDv1-A06](task_briefs/BUILDv1-A06.md) | 构建异步 I/O 与进程管理开发包 | CMake；Make or Ninja | 中型 |
| [BUILDv1-A07](task_briefs/BUILDv1-A07.md) | 构建带 TLS 支持的事件驱动库 | CMake；Make or Ninja | 中型 |
| [BUILDv1-A08](task_briefs/BUILDv1-A08.md) | 构建多编码正则与 JIT 开发包 | CMake；Make or Ninja | 中型 |
| [BUILDv1-A09](task_briefs/BUILDv1-A09.md) | 构建 HTTP/2 开发包与本地工具链 | CMake；Make or Ninja | 中型 |
| [BUILDv1-A10](task_briefs/BUILDv1-A10.md) | 构建可嵌入 Git 工作区管理开发包 | CMake；Make or Ninja | 中型 |

## B · 编译工具链与语言运行时

bootstrap、代码生成、大型链接与工具链测试。

| ID | 主工程与交付 | 构建系统 | 规划规模 |
|---|---|---|---|
| [BUILDv1-B01](task_briefs/BUILDv1-B01.md) | 构建并交付 LLVM/Clang 本机 C/C++ 工具链 | CMake；Ninja；TableGen；lit | 超大型 |
| [BUILDv1-B02](task_briefs/BUILDv1-B02.md) | 自举构建 GCC C/C++ 编译器与运行库 | Autoconf；GNU Make；DejaGnu | 超大型 |
| [BUILDv1-B03](task_briefs/BUILDv1-B03.md) | 构建并验收 ELF 汇编、链接与归档工具 | Autoconf；GNU Make；DejaGnu | 中型 |
| [BUILDv1-B04](task_briefs/BUILDv1-B04.md) | 构建含数据库与并发支持的 CPython 发行目录 | Autoconf；GNU Make；regrtest | 中型 |
| [BUILDv1-B05](task_briefs/BUILDv1-B05.md) | 构建 Node.js 并交付本地事件与国际化运行环境 | configure.py；GYP；GNU Make；Node test.py | 大型 |
| [BUILDv1-B06](task_briefs/BUILDv1-B06.md) | 构建并安装 Ruby 解释器与标准扩展 | Autoconf；GNU Make；Ruby test-unit；MSpec | 中型 |
| [BUILDv1-B07](task_briefs/BUILDv1-B07.md) | 构建 PHP 并验收 CLI 与 SQLite 数据处理 | Autoconf；GNU Make；PHPT | 中型 |
| [BUILDv1-B08](task_briefs/BUILDv1-B08.md) | 从源码构建 Go 工具链并交付本机开发环境 | cmd/dist；Go bootstrap；Go test | 大型 |
| [BUILDv1-B09](task_briefs/BUILDv1-B09.md) | 自举 Rust 编译器、标准库与文档工具 | bootstrap x.py；Cargo；CMake；Ninja；compiletest | 超大型 |
| [BUILDv1-B10](task_briefs/BUILDv1-B10.md) | 构建 OpenJDK 镜像并验收编译器与 JVM | Autoconf；GNU Make；javac bootstrap；jtreg；gtest | 大型 |

## C · 多媒体、图形与地理计算工程

模块/插件组合、原生依赖、资产与无头测试。

| ID | 主工程与交付 | 构建系统 | 规划规模 |
|---|---|---|---|
| [BUILDv1-C01](task_briefs/BUILDv1-C01.md) | 构建可安装的 CPU 媒体工具链并通过 FATE | configure；GNU Make | 大型 |
| [BUILDv1-C02](task_briefs/BUILDv1-C02.md) | 构建插件化媒体 SDK 与离线音视频管线 | Meson；Ninja | 大型 |
| [BUILDv1-C03](task_briefs/BUILDv1-C03.md) | 交付可开发和可测试的图像处理安装包 | Autoconf configure；GNU Make | 中型 |
| [BUILDv1-C04](task_briefs/BUILDv1-C04.md) | 构建流式图像处理 C/C++ SDK | Meson；Ninja | 中型 |
| [BUILDv1-C05](task_briefs/BUILDv1-C05.md) | 构建可复用的 CPU 视觉开发工具包 | CMake；Ninja | 大型 |
| [BUILDv1-C06](task_briefs/BUILDv1-C06.md) | 构建无界面的 Blender 场景处理与 CPU 渲染发行包 | CMake；Ninja | 超大型 |
| [BUILDv1-C07](task_briefs/BUILDv1-C07.md) | 构建 Godot 编辑器与 Linux 导出模板 | SCons | 大型 |
| [BUILDv1-C08](task_briefs/BUILDv1-C08.md) | 构建 CPU 软件图形栈并验证离屏执行 | Meson；Ninja | 大型 |
| [BUILDv1-C09](task_briefs/BUILDv1-C09.md) | 构建栅格与矢量数据开发发行包 | CMake；Ninja；SWIG | 大型 |
| [BUILDv1-C10](task_briefs/BUILDv1-C10.md) | 构建支持 CPU 离屏可视化的科学 SDK | CMake；Ninja | 超大型 |

## D · 数据库与基础设施软件

本地服务测试、进程/文件活动和临时状态。

| ID | 主工程与交付 | 构建系统 | 规划规模 |
|---|---|---|---|
| [BUILDv1-D01](task_briefs/BUILDv1-D01.md) | 构建并交付可嵌入应用的 PostgreSQL 工具链 | Autoconf；GNU Make | 中型 |
| [BUILDv1-D02](task_briefs/BUILDv1-D02.md) | 构建并验证 MariaDB 事务数据库发行包 | CMake；Ninja；MTR | 大型 |
| [BUILDv1-D03](task_briefs/BUILDv1-D03.md) | 构建可持久化的 Redis TLS 安装包 | GNU Make | 小型 |
| [BUILDv1-D04](task_briefs/BUILDv1-D04.md) | 交付经验证的 RocksDB 嵌入式存储 SDK | GNU Make | 大型 |
| [BUILDv1-D05](task_briefs/BUILDv1-D05.md) | 构建带 JSON 与 Parquet 的 DuckDB 分析 SDK | CMake；Ninja；GNU Make wrapper | 大型 |
| [BUILDv1-D06](task_briefs/BUILDv1-D06.md) | 构建可独立链接的 Arrow 列式数据 SDK | CMake；Ninja；CTest | 大型 |
| [BUILDv1-D07](task_briefs/BUILDv1-D07.md) | 构建并验证完整 ClickHouse 分析工具包 | CMake；Ninja | 超大型 |
| [BUILDv1-D08](task_briefs/BUILDv1-D08.md) | 构建可持久化的 etcd 发布工具包 | Go modules；official shell build | 中型 |
| [BUILDv1-D09](task_briefs/BUILDv1-D09.md) | 构建并交付支持 TLS 的 NGINX 代理包 | configure；GNU Make；Perl prove | 中型 |
| [BUILDv1-D10](task_briefs/BUILDv1-D10.md) | 构建并验证 Envoy 代理发行二进制 | Bazel；Bzlmod/declared repository dependencies | 超大型 |

## E · JVM 与 JavaScript 工程

依赖图、代码生成、包交付与运行时测试。

| ID | 主工程与交付 | 构建系统 | 规划规模 |
|---|---|---|---|
| [BUILDv1-E01](task_briefs/BUILDv1-E01.md) | 构建 Kafka 发行包并验收事件往返 | Gradle wrapper | 大型 |
| [BUILDv1-E02](task_briefs/BUILDv1-E02.md) | 构建 Spark SQL 发行包并交付本地分析程序 | Maven；Spark build/mvn wrapper | 超大型 |
| [BUILDv1-E03](task_briefs/BUILDv1-E03.md) | 构建 Flink 发行包并验收本地流处理 | Maven wrapper | 超大型 |
| [BUILDv1-E04](task_briefs/BUILDv1-E04.md) | 构建 Lucene 库并交付可重载索引示例 | Gradle wrapper | 大型 |
| [BUILDv1-E05](task_briefs/BUILDv1-E05.md) | 构建本机 Elasticsearch 分发并验收查询 | Gradle wrapper | 超大型 |
| [BUILDv1-E06](task_briefs/BUILDv1-E06.md) | 构建 TypeScript 编译器包并验收类型检查 | npm；Hereby；esbuild bootstrap | 中型 |
| [BUILDv1-E07](task_briefs/BUILDv1-E07.md) | 构建 Rollup 的 JS 与原生解析器分发 | npm；Cargo；napi-rs；wasm-pack；Rollup bootstrap | 大型 |
| [BUILDv1-E08](task_briefs/BUILDv1-E08.md) | 构建 Babel 工具链并验收跨版本转译 | Yarn；Make；Babel bootstrap | 中型 |
| [BUILDv1-E09](task_briefs/BUILDv1-E09.md) | 构建 esbuild 本机工具并验收打包接口 | Make；Go；Node.js scripts | 小型 |
| [BUILDv1-E10](task_briefs/BUILDv1-E10.md) | 构建 SWC 原生 Node 扩展并验收转译 | Cargo；pnpm；napi-rs | 大型 |

## F · 机器学习与数值计算框架

混合语言 native 编译、框架链接与 wheel/库交付。

| ID | 主工程与交付 | 构建系统 | 规划规模 |
|---|---|---|---|
| [BUILDv1-F01](task_briefs/BUILDv1-F01.md) | 构建并交付 CPU PyTorch 发行包及扩展开发环境 | CMake；Ninja；scikit-build-core；PEP 517 | 超大型 |
| [BUILDv1-F02](task_briefs/BUILDv1-F02.md) | 从源码交付 TensorFlow CPU wheel 与可重载模型支持 | Bazel；PEP 517 wheel target | 超大型 |
| [BUILDv1-F03](task_briefs/BUILDv1-F03.md) | 编译 JAX 的 CPU jaxlib/XLA 并交付配套 wheel | Bazel；JAX build/build.py；setuptools；PEP 517 | 超大型 |
| [BUILDv1-F04](task_briefs/BUILDv1-F04.md) | 构建 scikit-learn 原生扩展发行包并验证邻域搜索与模型流水线 | Meson；Ninja；meson-python；PEP 517 | 中型 |
| [BUILDv1-F05](task_briefs/BUILDv1-F05.md) | 编译 NumPy 数组运行时及开发接口发行包 | Meson；Ninja；meson-python；PEP 517 | 中型 |
| [BUILDv1-F06](task_briefs/BUILDv1-F06.md) | 构建 SciPy 多语言数值 wheel 并验证线性代数与优化 | Meson；Ninja；meson-python；PEP 517 | 大型 |
| [BUILDv1-F07](task_briefs/BUILDv1-F07.md) | 构建 pandas Cython 发行包并验收分组与时间索引 | Meson；Ninja；meson-python；PEP 517 | 中型 |
| [BUILDv1-F08](task_briefs/BUILDv1-F08.md) | 构建 XGBoost 原生核心与 Python 发行包 | CMake；Ninja；Python package backend | 大型 |
| [BUILDv1-F09](task_briefs/BUILDv1-F09.md) | 构建 LightGBM CPU 命令行与原生 SDK | CMake；Ninja；GoogleTest | 中型 |
| [BUILDv1-F10](task_briefs/BUILDv1-F10.md) | 构建 ONNX Runtime CPU wheel 与原生运行库 | CMake；ONNX Runtime build.sh；Python wheel packaging | 大型 |

