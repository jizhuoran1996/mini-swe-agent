# BUILDv1-B04 · 构建含数据库与并发支持的 CPython 发行目录

Build a CPython installation with database and concurrency support

**主工程**：[CPython](https://github.com/python/cpython)  
**组别**：编译工具链与语言运行时　**规划规模**：中型　**实施优先级**：pilot

**语言**：C；Python  
**构建系统**：Autoconf；GNU Make；regrtest  
**Canonical goal**：`cpython-runtime-source-build`

## Agent 任务目标

交付独立安装的 Python 解释器及标准库，支持 JSON、SQLite、子进程、线程和异步工作流，并证明新建应用环境使用本轮编译的解释器和扩展。

## 官方工作流与派生方式

CPython configure/make/install and regrtest module selections

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置 C 编译器及 SQLite、OpenSSL、libffi、zlib、bz2/lzma 等锁定开发依赖；未准备目标解释器对象。

## 需要完成的工作

- 完整编译 CPython 和声明的标准库扩展，检查 configure/module detection。
- 运行冻结的 regrtest 模块集合并安装到 session 前缀。
- 从新安装创建无 pip 的 venv，在源树外运行消费者。

## 目标范围

本机 CPython、完整标准库安装及声明的 SQLite/压缩/FFI/TLS 扩展；无第三方 pip 应用包。

## 构建与测试入口

### Configure / Generate

- 在 BUILD_ROOT 执行 "$SRC_ROOT/configure" --prefix="$INSTALL_ROOT"

### Build

```bash
make -C "$BUILD_ROOT" -j"$BUILD_JOBS"
```

### Package / Install

```bash
make -C "$BUILD_ROOT" install
```

- 归档完整解释器、标准库和 lib-dynload；记录精确 PYTHON_BIN 路径。

### Official Tests

- 在 BUILD_ROOT 运行 ./python -m test -j "$TEST_JOBS" test_json test_sqlite3 test_importlib test_threading test_subprocess test_asyncio

- 冻结 revision 后将上述模块解析成测试文件清单，并收集每个模块的执行/跳过结果。

## 官方测试选择

- **reference**：test_json、test_sqlite3、test_importlib、test_threading、test_subprocess、test_asyncio
- **rationale**：覆盖编码、数据访问、模块加载和真实并发/子进程；不打开 regrtest 的外部网络或大资源选项。
- **counts**：测试模块名在锁定源树验证；缺扩展导致应执行模块整体 skip 视为失败。

## 独立消费者验收

- 新 PYTHON_BIN -m venv --without-pip 创建消费者环境；检查 sys.executable、sys.prefix 及动态扩展 __file__。
- 源树外执行 JSON→SQLite→查询流程、启动子进程并完成异步任务，断言结果。
- SQLite/SSL 等声明扩展不能来自预安装 release；系统共享依赖按预置清单允许。

## 交付物

- cpython-install.tar.gz
- 构建选项及扩展清单
- regrtest 报告
- 新 venv 消费者输出与路径证明

## 后续使用

使用已安装解释器创建第二个独立应用环境并处理新增输入，验证安装树可重复使用且不依赖构建目录。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 CPython 与数据库/编码扩展
- **tests**：test_json/test_sqlite3/test_importlib
- **deliverable**：可安装解释器和标准库

### Reference：正式参考配置

- **scope**：上述范围加并发/子进程消费者
- **tests**：六个命名模块
- **deliverable**：可服务普通开发工作流的解释器安装

### Extended：扩展范围

- **scope**：同一解释器的全部默认本机标准库回归
- **tests**：python -m test，不使用 -u all；固定因环境缺失允许跳过项
- **deliverable**：相同安装树与更广官方验证

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。

## 预期资源形态

- c_compilation
- extension_linking
- process_creation
- python_test_imports
- filesystem_metadata
- install_workspace

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。

## 离线依赖准备

- 源码和系统开发依赖预装；安装过程中的 ensurepip 仅允许源码附带的锁定 wheels。
- 消费者使用 --without-pip，正式任务不访问 PyPI。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 解释器/扩展 identity 属于本轮；选定模块确实执行。
- 新 venv 的所有消费者断言通过，且源树不可见时仍可导入。

## 应拒绝的负例

- configure 静默省略 SQLite/SSL 等合同扩展。
- 消费者从源树或系统 Python 导入造成假通过。
- 测试模块名字解析失败导致零测试。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- CPython 单一上游；其作为其他任务 bootstrap Python 的共享依赖单独记账。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。

## 官方来源

- [B_PYTHON_BUILD] [CPython setup and building](https://devguide.python.org/getting-started/setup-building/) — 检查位置：Unix build; build dependencies
- [B_PYTHON_TEST] [Running and writing CPython tests](https://devguide.python.org/testing/run-write-tests/) — 检查位置：Running tests; selecting tests; parallel tests
- [B_PYTHON_README] [CPython README](https://github.com/python/cpython/blob/main/README.rst) — 检查位置：Build instructions; Testing; Installing multiple versions

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
