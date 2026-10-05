# BUILDv1-F09 · 构建 LightGBM CPU 命令行与原生 SDK

Build the LightGBM CPU command-line tool and native SDK

**主工程**：[LightGBM](https://github.com/lightgbm-org/LightGBM)  
**组别**：机器学习与数值计算框架　**规划规模**：中型　**实施优先级**：pilot

**语言**：C++；C  
**构建系统**：CMake；Ninja；GoogleTest  
**Canonical goal**：`build_install_verify_lightgbm_linux_cpu`

## Agent 任务目标

从源码交付可安装的 LightGBM CLI、共享库及头文件，通过官方 C++ 测试，并让独立 C API 应用使用新构建库完成模型加载与预测。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 锁定源码与 external_libs、C++/OpenMP/CMake/Ninja 和 GTest；提供官方 examples 的小数据和配置，不含 lightgbm 二进制。

## 需要完成的工作

- 完整构建 CLI、共享库和 testlightgbm。
- 安装到用户级 prefix，归档可交付目录。
- 运行官方 C++ 测试；用新 CLI 产生模型，再由新编译 C API consumer 读取。

## 目标范围

CPU/OpenMP LightGBM CLI 和 C API SDK；Python wheel 可作为扩展，baseline 本身已交付可安装的 native 工程。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -GNinja -DBUILD_CLI=ON -DBUILD_CPP_TEST=ON -DUSE_GPU=OFF -DUSE_CUDA=OFF -DUSE_MPI=OFF -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT"
```

- GTest 必须预载或以固定 FetchContent 源提供；不在测量期间拉取 Git 仓库。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT" --prefix "$INSTALL_ROOT"
```

- 按 install_manifest 打包 bin/lib/include 与许可证；C API consumer 链接该 prefix 内共享库。

### Official Tests

- 运行本轮实际生成的 testlightgbm --gtest_output=xml:<report>；官方 Linux 构建将 testlightgbm 放在源码根目录。

- 先记录 --gtest_list_tests，再核对测试结果覆盖同一已冻结 CPU 清单。

## 官方测试选择

- **core**：完整官方 testlightgbm C++ CPU suite。
- **reference**：同一 C++ suite，加官方小型 binary/regression 示例的 CLI→C API 消费验证。
- **extended**：增加 Python wrapper wheel 与对应官方本地 tests，或独立 SWIG Java wrapper 编译 profile。
- **rationale**：CMake 已列出 array/buffer/serialization 等实际 tests；CLI 与 C API 验收覆盖安装后的使用链。

## 独立消费者验收

- 检查安装 CLI/库/headers 均由本轮构建生成，ldd 或实际进程映射证明 consumer 使用 INSTALL_ROOT 中的库。
- 用官方预载小数据训练短模型，再用独立 C API 程序加载并对固定行预测，与本轮 CLI 结果对照。
- 移开源码/build 路径后 consumer 仍能运行；不允许依赖未声明的源码树 shared library。

## 交付物

- LightGBM bin/lib/include 安装归档。
- CMake install manifest、C++ tests XML、独立 consumer 源码和执行报告。

## 后续使用

新应用拿到交付 SDK，编译模型预测 consumer 并处理新增数据；复用安装产物而非源码树的可执行文件。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：supported_configuration_delta
- **patch_binding**：null
- **description**：可保留构建树将官方 BUILD_STATIC_LIB 配置改为静态 SDK，并重新编译、打包及静态链接 consumer；明确重新配置实际触发范围，不声称所有对象都可复用。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：CPU CLI/shared SDK + C++ suite。

### Reference：正式参考配置

- **scope**：上述交付，加 CLI 模型与独立 C API 消费。

### Extended：扩展范围

- **scope**：增加官方 Python/SWIG wrapper 或独立 CUDA/OpenCL 编译配置，按能力准入。

## 可控变量

- 冻结编译并发、测试并发、OpenMP/BLAS 线程数及 CPU 指令集。
- 资源限额为独立实验条件；依赖缓存与目标对象/安装缓存分开。

## 预期资源形态

- compiler_cpu
- linker_memory
- process_creation
- filesystem_metadata
- build_workspace
- test_subprocesses

## 后端能力要求

- Linux x86_64，可作为普通用户执行编译/链接/测试和 Python 子进程。
- 提供可写盘、共享内存/线程能力；CPU baseline 不要求 GPU/root/外部集群。

## 离线依赖准备

- 预载 external_libs/fmt/Eigen/nanoarrow 等该版本源码依赖以及 GTest。
- 提供预先固定的小型官方 example 输入；测试与编译不访问下载服务。

## 回放与状态

- 真实保持 configure→build→package/install→test 的完成依赖，保存全部子进程退出状态。
- 冻结 source/config/test 清单和路径角色；重放不复用旧 PID、旧产物或旧测试日志。

## 最终 oracle

- 检查产物身份、构建来源和新消费环境内实际加载的 native libraries；不得由预装包满足验收。
- 报告 collected/selected/executed/skipped/failed；空套件、错误选择或无解释的全 skip 不算完成。

## 应拒绝的负例

- 提供公开发行二进制或只有 metadata 的包应失败。
- 遗漏 native library、加载旧安装或漏跑声明的官方 tests 应失败。

## Builder 实施工作

- 固定相容 source/submodule/toolchain/dependency hash。
- 实现事件采集、测试清单冻结和独立消费端验收；测出参考资源画像后准入。

## 源码血缘

- LightGBM 官方仓库现为 lightgbm-org/LightGBM（原 microsoft 路径重定向）。
- 原生 CLI/SDK 交付与旧 GPU training 任务用途不同。

## 与已有任务的关系

可能与旧 CPU/Memory/GPU 组共享软件来源；本次目标是构建、打包和验收工程产物。

## 范围说明

- planned_scale_class 是设计等级，尚未测得构建时间和内存/磁盘需求。
- 测试与产物容差以固定版本为准；不要求带时间戳的 wheel/archive 全字节相等。

## 官方来源

- [F_LGB_BUILD] [LightGBM installation and unit-test guide](https://lightgbm.readthedocs.io/en/latest/Installation-Guide.html) — 检查位置：Linux CPU build; C++ unit tests; options
- [F_LGB_CMAKE] [LightGBM CMake targets](https://github.com/lightgbm-org/LightGBM/blob/main/CMakeLists.txt) — 检查位置：BUILD_CLI; BUILD_CPP_TEST; install; GoogleTest dependency
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
