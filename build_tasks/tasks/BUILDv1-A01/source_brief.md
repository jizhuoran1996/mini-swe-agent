# BUILDv1-A01 · 构建并交付 zlib 压缩开发包

Build and deliver a validated zlib development package

**主工程**：[zlib](https://github.com/madler/zlib)  
**组别**：原生基础库与命令行工具　**规划规模**：小型　**实施优先级**：pilot

**语言**：C  
**构建系统**：configure；GNU Make  
**Canonical goal**：`build-test-install/zlib`

## Agent 任务目标

从源码生成可被新 C 工程使用的 zlib 开发包，保留静态和动态链接方式，并证明 gzip 流与内存压缩结果正确。

## 官方工作流与派生方式

README Unix workflow and Makefile.in all/teststatic/testshared/test64/install

## 初始环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

## 需要完成的工作

- 配置到私有前缀，从干净源树编译完整压缩库和自带 example/minigzip 测试程序。
- 运行静态/共享链接两套官方检查，安装头文件、库及 pkg-config 元数据。
- 在源码树之外编译新 consumer，对分块压缩和 gzip 文件往返验证，交付归档与安装清单。

## 目标范围

参考：libz.a、libz.so 与头文件/pkg-config；example/minigzip、examplesh/minigzipsh 留作官方测试产物。

## 构建与测试入口

### 工作目录

- SRC_ROOT；源码副本同时承载该上游 Makefile 的构建输出。

### Configure / Generate

- ./configure --prefix="$INSTALL_ROOT"

### Build

```bash
make -j "$BUILD_JOBS"
```

### Package / Install

```bash
make install
```

- 将 INSTALL_ROOT 内容归档到 ARTIFACT_ROOT，并包含版本、配置与安装文件清单。

### Official Tests

```bash
make test
```

- 扩展执行 make test64；该目标来自 Makefile.in，需纳入固定测试预算。

## 官方测试选择

- **reference**：teststatic；testshared
- **command**：make test
- **rationale**：覆盖实际编译的静态/动态实现以及 deflate/inflate、gzip 和校验路径；避免只检查版本字符串。
- **extended**：test64
- **counting**：解析每个命名目标和 example 内部检查；不把终端一条 OK 当作未知数量完整测试。

## 独立消费者验收

- 从安装前缀编译独立 C 程序，调用 compress2/uncompress 比较原文，并以 gzwrite/gzread 检查文件流。
- 动态 consumer 的加载映射必须指向 INSTALL_ROOT；静态 consumer 的链接命令必须使用本轮 libz.a。
- 使用含二进制字节与多块输入的固定小 fixture；截断输入须返回错误。

## 交付物

- zlib 开发包归档与文件 hash 清单
- 配置和完整构建/测试日志
- 独立 consumer 源码、可执行文件及往返报告

## 后续使用

- **request**：用已安装开发包为另一批本地文件生成 gzip 归档，再在新进程中读取并校验。
- **state**：已安装库、头文件和配置保留；新 consumer 不读取源码树产物。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：optional_source_patch
- **patch_binding**：null
- **plan**：保留已完成构建树后，可绑定一个真实上游修复或功能 patch 及专属验收；patch、基线与受影响测试须在采集前冻结。默认任务无需修改源代码。
- **identity_rule**：保持同一 task ID；无改动或仅 touch 的重建只作诊断。

## 同一任务的规模配置

### Core：最小完整交付

完整静态库与 teststatic，适于最小工程调通。

### Reference：正式参考配置

静态+共享库的完整默认构建和 make test。

### Extended：扩展范围

增加来源已定义的 all64/test64 文件偏移接口检查；仍是同一项目。

## 可控变量

- 构建并行度 BUILD_JOBS 与测试并行度 TEST_JOBS 分别冻结；不以重复相同构建增加规模。
- 参考/扩展通过声明的真实目标、特性和官方测试范围改变工作；冷/热缓存及 Debug/Release 单列为情景。

## 预期资源形态

- short_native_compile
- configure_probes
- static_and_shared_link
- small_file_metadata

## 后端能力要求

- Linux x86_64；常规 C/C++ 工具链执行、fork/exec、文件与符号链接可用。
- 使用普通用户及私有安装前缀，不安装到系统目录。

## 离线依赖准备

- 预装 C 编译器、binutils、Make、POSIX shell；无需获取外部源码依赖。
- 源内 example/minigzip 和固定 consumer fixture 随初始镜像提供。

## 回放与状态

- 每次默认回放均从相同源码和依赖状态重新编译；记录的模型等待不替代编译、链接或测试。
- 等待真实进程和测试子进程结束；保留 build tree、临时文件、退出码与产物，下一步依赖本轮完成。
- 测试端口、PID 与临时路径绑定本轮值；时间戳/build ID 导致的字节差异不默认视为功能失败。

## 最终 oracle

- 独立记录源码版本、配置、安装清单与产物身份；禁止系统预装同名库/程序替代。
- 测试 inventory 必须非空，冻结选择并记录 discovered/selected/executed/skipped/failed；错误或空套件不能因返回 0 通过。

## 应拒绝的负例

- 删除必需安装产物后新 consumer 必须失败，不能从系统路径补回。
- 取消测试、错误版本或未经声明跳过必测项，必须被验收拒绝。

## Builder 实施工作

- 绑定正式 release/commit、源与依赖 hash，并解析匹配工具链。
- 实现安装身份检查和独立 consumer，冻结测试清单与环境所需能力。
- 真实构建、采集及参考画像后再分配资源标签；当前规模级别为规划。

## 源码血缘

- primary_project: zlib；relationship: one upstream project; dependencies and build profiles do not add independent tasks

## 与已有任务的关系

若旧资源包使用同一软件，其运行时处理任务与本题源码构建/测试交付目标分别记账，并保留共享软件来源。

## 范围说明

- 尚未在参考 sandbox 实测构建耗时、RAM、空间或系统调用量；以固定实例实际 profiling 为准。

## 官方来源

- [A_ZLIB_README] [zlib build overview](https://github.com/madler/zlib) — 检查位置：README: Unix build, examples and license
- [A_ZLIB_MAKE] [zlib Makefile targets](https://github.com/madler/zlib/blob/develop/Makefile.in) — 检查位置：all, static, shared, teststatic, testshared, test64, install
- [A_ZLIB_CONFIG] [zlib configure switches](https://github.com/madler/zlib/blob/develop/configure) — 检查位置：option parser: --prefix, --static, --64, --zprefix

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
