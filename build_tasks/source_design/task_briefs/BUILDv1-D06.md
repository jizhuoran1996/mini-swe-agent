# BUILDv1-D06 · 构建可独立链接的 Arrow 列式数据 SDK

Build an Arrow C++ columnar data SDK

**主工程**：[Apache Arrow](https://github.com/apache/arrow)  
**组别**：数据库与基础设施软件　**规划规模**：大型　**实施优先级**：standard

**语言**：C++；CMake；Python test helpers  
**构建系统**：CMake；Ninja；CTest  
**Canonical goal**：`build.install.verify.apache_arrow`

## Agent 任务目标

为离线数据转换应用构建 Arrow C++ SDK，提供 CSV、IPC 和 Parquet 互操作能力，并让新的消费者在安装目录之外完成格式往返。

## 官方工作流与派生方式

Arrow C++ 官方 component build、CSV/IPC/Parquet test targets 与 SDK installation。

## 初始环境

- 固定版本的完整源代码、声明的子模块和测试数据已预置；目标项目的对象文件、已编译库、测试结果和安装目录为空。
- 编译器、引导工具及第三方依赖来源与版本写入输入清单；依赖缓存和本任务产物缓存分别管理。

## 需要完成的工作

- 从 Arrow cpp 源码配置明确组件，编译库和测试目标；依赖选用已安装快照或指定本地 source artifact。
- 运行三个对应格式的官方 CTest 测试，核对枚举、依赖与 fixture。
- 安装并编译独立 C++ 消费者，验证 nullable/schema/数值列的往返结果。

## 目标范围

Arrow C++ core/compute/CSV/IPC 与 Parquet；基线不启用 Flight、S3、GCS、CUDA、Gandiva 或 Python wheel。

## 构建与测试入口

### Configure / Generate

- cmake -S "$SRC_ROOT/cpp" -B "$BUILD_ROOT" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DARROW_BUILD_TESTS=ON -DARROW_COMPUTE=ON -DARROW_CSV=ON -DARROW_IPC=ON -DARROW_PARQUET=ON -DARROW_DEPENDENCY_SOURCE=SYSTEM；全部所需包必须已安装。

- 若采用 BUNDLED，使用官方 thirdparty/download_dependencies.sh 预备阶段生成的 ARROW_*_URL 指向本地归档，并将配置写入 manifest。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

- cmake --install "$BUILD_ROOT"；打包 Arrow/Parquet 库、头文件与 CMake/pkg-config 导出。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -N -R "^(arrow-csv-test|arrow-ipc-read-write-test|parquet-arrow-reader-writer-test)$"
```

```bash
ctest --test-dir "$BUILD_ROOT" --output-on-failure -R "^(arrow-csv-test|arrow-ipc-read-write-test|parquet-arrow-reader-writer-test)$"
```

## 官方测试选择

- **official_entrypoints**：arrow-csv-test；arrow-ipc-read-write-test；parquet-arrow-reader-writer-test
- **selection**：三个 CMake 注册的官方格式测试，使用预置 arrow-testing 与 parquet-testing 数据；实例绑定时对名称和数量作硬校验。
- **rationale**：测试实际交付的格式读写栈，避免误把依赖生成器或空 CTest 项当验证。

## 独立消费者验收

- 在独立目录通过 INSTALL_ROOT 中的 CMake package 或 pkg-config 构建 C++ 程序，记录实际链接的 Arrow/Parquet 动态库。
- 创建带 null、字符串和数值列的 Arrow table，写 IPC 与 Parquet；新进程回读，检查 schema、null 位置、行序和结果值。
- 加入 CSV 输入并独立校验计算/导出结果，不从源树运行已有 example 代替安装消费者。

## 交付物

- Arrow/Parquet SDK 安装归档
- 三个 CTest 条目及其 gtest 计数/结果
- 独立消费者源码、格式产物和 schema/value 校验报告

## 后续使用

使用已交付 SDK 接收含新增可空列的数据分片，生成兼容 IPC/Parquet 产物并检查新旧 schema 处理。

## 可选增量变化

- **default**：False
- **kind**：optional_legitimate_patch
- **binding_status**：builder_must_bind_patch_before_collection
- **description**：主任务是干净构建。若增加增量场景，先冻结具有功能意义的上游补丁或已验证配置变更、受影响目标和对应验收；保留同一任务 ID。仅 touch/no-op 不作为独立任务。

## 同一任务的规模配置

### Core：最小完整交付

Arrow core/IPC + IPC read-write test 与消费者。

### Reference：正式参考配置

加入 compute/CSV/Parquet，运行对应三个格式测试并交付完整转换 SDK。

### Extended：扩展范围

显式启用 DATASET/FILESYSTEM 并扩展到这些组件的官方本地测试；Flight/外部服务需单独能力 profile。

## 可控变量

- 固定实际目标与测试集合；编译并行度和测试并行度独立记录。
- 干净构建为基线；缓存、优化级别和增量模式作为实验场景，不能作为新任务计数。
- 实际资源分类依据参考画像；不预设编译耗时、峰值内存或 syscall 数量。

## 预期资源形态

- large C++ templates
- multi-library link
- format code generation
- test fixtures
- installed headers
- artifact roundtrip

## 后端能力要求

- Linux x86_64、普通用户、可写工作目录、真实子进程与文件锁；所需 ABI 和工具链随实例固定。

## 离线依赖准备

- 源代码、子模块、依赖、测试 fixture 与工具链在计时前准备；正式构建禁止隐式访问公网。
- 目标项目由源码重新编译；预置工具/依赖的许可、校验和与来源单列。
- 预置完整 arrow-testing/parquet-testing 数据并设置 ARROW_TEST_DATA/PARQUET_TEST_DATA；JSON test 依赖、gtest、压缩库、locale 和 Python helper 固定。

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
- CSV/IPC/Parquet 某组件关闭但配置与报告宣称支持；消费者依赖系统 Arrow。

## Builder 实施工作

- 固定源码 revision、工具链和完整依赖快照；实现 source/install/test 产物清单。
- 将官方命令包装为资源可追踪的任务环境，绑定测试集合、端口及真实完成事件。
- 为锁定的 Arrow revision 枚举 CTest 名称，要求三个设计条目全部存在；固定源码和依赖版本后再测量。
- 首次真实构建时冻结官方测试的精确数量、消费者期望结果与合理 timeout；不存在实测资源数值。

## 源码血缘

- Arrow 和 Arrow C++ 所包含的 Parquet 实现属于同一个项目任务。
- 与 GPU 数据处理及 I/O 格式转换共享基础格式库，不能按两次软件多样性重复报告。

## 与已有任务的关系

与此前资源任务可能共享软件来源；本题交付源码构建与测试后的工程产物，区别于只运行该软件处理数据。

## 范围说明

- 规模标签是规划，实际成本待参考构建画像；本任务不要求外部生产部署或跨宿主集群。

## 官方来源

- [D_ARROW_BUILD] [Building Arrow C++](https://arrow.apache.org/docs/developers/cpp/building.html) — 检查位置：Building and running tests; component options; offline dependency builds
- [D_ARROW_CSV] [Arrow CSV test target](https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/csv/CMakeLists.txt) — 检查位置：add_arrow_test(csv-test) and installed headers
- [D_ARROW_IPC] [Arrow IPC test targets](https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/ipc/CMakeLists.txt) — 检查位置：ADD_ARROW_IPC_TEST and read_write_test
- [D_ARROW_PARQUET] [Arrow Parquet test targets](https://raw.githubusercontent.com/apache/arrow/main/cpp/src/parquet/CMakeLists.txt) — 检查位置：ADD_PARQUET_TEST and arrow-reader-writer-test
- [D_ARROW_TESTUTIL] [Arrow test naming and registration](https://raw.githubusercontent.com/apache/arrow/main/cpp/cmake_modules/BuildUtils.cmake) — 检查位置：ADD_TEST_CASE, prefix joining, underscore-to-hyphen conversion, unittest label
- [D_ARROW_CORE_CMAKE] [Arrow C++ test prefix wrapper](https://raw.githubusercontent.com/apache/arrow/main/cpp/src/arrow/CMakeLists.txt) — 检查位置：ADD_ARROW_TEST function lines 262–290; default prefix arrow and delegation to add_test_case

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
