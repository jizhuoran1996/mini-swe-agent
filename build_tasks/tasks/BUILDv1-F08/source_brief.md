# BUILDv1-F08 · 构建 XGBoost 原生核心与 Python 发行包

Build the XGBoost native core and Python distribution

**主工程**：[XGBoost](https://github.com/dmlc/xgboost)  
**组别**：机器学习与数值计算框架　**规划规模**：大型　**实施优先级**：standard

**语言**：C++；Python  
**构建系统**：CMake；Ninja；Python package backend  
**Canonical goal**：`build_install_verify_xgboost_linux_cpu`

## Agent 任务目标

从源码交付 CPU libxgboost 和包含该库的 Python wheel，通过 C++/Python 官方基础测试，证明新的应用能够训练、保存和加载一个小型树模型。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 固定 dmlc-core 等 submodules、C++ 工具链、OpenMP、GoogleTest、Python 构建依赖，以及仓库的 agaricus 小型测试数据。

## 需要完成的工作

- 构建 CPU native core 和 testxgboost。
- 按上游 Python 包流程将本轮共享库打入 wheel；核对打包实际使用的 native library。
- 运行官方 tests 并在新 venv 验收模型保存/加载。

## 目标范围

CPU C++ shared library、官方 C++ tests 和 Python wheel；默认无需 CUDA/NCCL/MPI 或 Dask/Spark 集群。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -GNinja -DCMAKE_BUILD_TYPE=Release -DUSE_CUDA=OFF -DGOOGLE_TEST=ON -DUSE_OPENMP=ON
```

- 其余联邦/GPU/分布式插件保持 manifest 中的明确关闭状态；子模块已离线就绪。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
python -m build --wheel --no-isolation --outdir "$ARTIFACT_ROOT" "$SRC_ROOT/python-package"
```

- 按固定版本 backend 的重用路径打包本轮 libxgboost.so；若 backend 重新编译则计入并记录，不能载入系统旧库。

```bash
"$INSTALL_ROOT/bin/python" -m pip install --no-index --no-deps "$ARTIFACT_WHEEL"
```

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" --output-on-failure -R "^TestXGBoostLib$"
```

- 使用本轮 wheel 环境执行 python -m pytest "$SRC_ROOT/tests/python/test_basic.py" --import-mode=importlib；agaricus fixture 路径随实例提供。

## 官方测试选择

- **core**：TestXGBoostLib（来自 CMake add_test）与 wheel 消费检查。
- **reference**：TestXGBoostLib + tests/python/test_basic.py。
- **extended**：增补已冻结本地 tree/data/model-I/O CPU tests；JVM 或 CUDA 编译须独立 profile 准入。
- **rationale**：检测 native core、Python binding、DMatrix 和序列化整合，不以大型训练吞吐作为工程正确性。

## 独立消费者验收

- 检查 xgboost.core._LIB 实际路径、wheel 中 libxgboost.so 与打包记录；禁止动态链接到系统旧版本。
- 用固定小型 CPU 数据做短训练，保存为声明模型格式；新进程重载，对同输入预测一致。
- C API 或 Python build-info 验证所需 CPU/OpenMP 功能与 manifest 相符。

## 交付物

- libxgboost.so 和本轮 Python wheel。
- CMake/测试报告、打包库来源及模型重载消费报告。

## 后续使用

接收新样本，用交付模型和本轮安装进行预测；可选构建变体才加入新的源码功能补丁。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：optional_frozen_functional_patch
- **patch_binding**：null
- **description**：主任务先完成 clean build。可选真实功能补丁必须由实例构建者绑定提交/patch 和独立验收后，再复用原构建树；未绑定时不生成修复步骤。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：CPU core、C++ tests、Python wheel 与独立消费。

### Reference：正式参考配置

- **scope**：增加官方 basic Python tests 和完整模型重载验收。

### Extended：扩展范围

- **scope**：增加已绑定 CPU test suites 或独立 CUDA/JVM packaging profile；不新增任务 ID。

## 可控变量

- 冻结编译并发、测试并发、OpenMP/BLAS 线程数及 CPU 指令集。
- 资源限额为独立实验条件；依赖缓存与目标对象/安装缓存分开。
- 冻结 native_library_packaging_route 及库来源；选择重用或双构建后不得根据后端或缓存状态变更。

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

- 预载 submodules、GoogleTest、Python build/test wheels 与 agaricus fixtures。
- 清理初始 lib/libxgboost.so 和目标 cache；系统同名库不作为打包来源。

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
- 实例冻结唯一 native-library 打包路线：使用官方 backend 的本轮库重用路径并检查前后 hash，或显式第二次 native build。所有后端执行同一路线，不允许运行中自动选择。第二次编译时固定同一 CPU/OpenMP 设置，计入真实工作并单独验证 wheel。

## 源码血缘

- XGBoost；与 LightGBM 为不同实现/交付工程，但共享 CMake/OpenMP 类工具链。
- 此前 GPU pack 的 boosted-tree 工作负载与本题编译工程目标分开。

## 与已有任务的关系

可能与旧 CPU/Memory/GPU 组共享软件来源；本次目标是构建、打包和验收工程产物。

## 范围说明

- planned_scale_class 是设计等级，尚未测得构建时间和内存/磁盘需求。
- 测试与产物容差以固定版本为准；不要求带时间戳的 wheel/archive 全字节相等。

## 官方来源

- [F_XGB_BUILD] [XGBoost build from source](https://xgboost.readthedocs.io/en/stable/build.html) — 检查位置：Shared library; Python source package
- [F_XGB_CMAKE] [XGBoost CMake build targets](https://github.com/dmlc/xgboost/blob/master/CMakeLists.txt) — 检查位置：USE_CUDA; USE_OPENMP; GOOGLE_TEST; testxgboost
- [F_XGB_TEST] [XGBoost basic Python tests](https://github.com/dmlc/xgboost/blob/master/tests/python/test_basic.py) — 检查位置：tests/python/test_basic.py
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
