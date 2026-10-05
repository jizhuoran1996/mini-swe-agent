# BUILDv1-F06 · 构建 SciPy 多语言数值 wheel 并验证线性代数与优化

Build a SciPy numerical wheel and verify linear algebra and optimization

**主工程**：[SciPy](https://github.com/scipy/scipy)  
**组别**：机器学习与数值计算框架　**规划规模**：大型　**实施优先级**：standard

**语言**：Python；C；C++；Fortran；Cython；Pythran  
**构建系统**：Meson；Ninja；meson-python；PEP 517  
**Canonical goal**：`build_install_verify_scipy_linux_cpu`

## Agent 任务目标

从源码交付具有数值原生扩展的 SciPy wheel，使下游环境能够求解线性系统和约束优化问题，并通过对应官方模块测试。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 提供固定 C/C++/Fortran 编译器、BLAS/LAPACK、NumPy ABI、Cython/Pythran/pybind11、Meson 及测试依赖。

## 需要完成的工作

- 编译声明范围的完整 wheel，记录 Fortran/Cython/Pythran 生成和链接步骤。
- 在本轮 wheel 环境运行 linalg 和 optimize 的官方 CPU tests。
- 新消费端对已知解问题计算残差/目标函数并核查动态依赖。

## 目标范围

完整 Linux CPU SciPy wheel；reference 验证 linalg/optimize，扩展范围增加真实官方模块而非反复求解同一小问题。

## 构建与测试入口

### Configure / Generate

- 固定 BLAS/LAPACK、整数 ABI、C/C++/Fortran 工具链及 mesonpy 配置。

- 冻结 SCIPY_HYPOTHESIS_PROFILE 和 SCIPY_XSLOW；reference 不启用 xslow。

### Build

```bash
python -m build --wheel --no-isolation --outdir "$ARTIFACT_ROOT" "$SRC_ROOT"
```

- 构建并发使用 Meson 的 compile-args；若采用 spin 开发流程，仍另外产出并验收正式 wheel。

### Package / Install

```bash
"$INSTALL_ROOT/bin/python" -m pip install --no-index --no-deps "$ARTIFACT_WHEEL"
```

### Official Tests

- core: python -m pytest --pyargs scipy.linalg -m "not slow"

- reference: python -m pytest --pyargs scipy.linalg scipy.optimize -m "not slow"；与官方 spin test -s 子模块选择等价，固定测试依赖和 CPU array backend。

## 官方测试选择

- **core**：scipy.linalg 非 slow suite。
- **reference**：scipy.linalg 与 scipy.optimize 的非 slow suite；未启用 SCIPY_XSLOW。
- **extended**：增加 scipy.sparse 与 scipy.signal，或经过资源准入的 slow tests；使用官方 spin/pytest 模块选择。
- **rationale**：覆盖多语言扩展、BLAS/LAPACK、优化求解器及 Python ABI，完整构建与测试覆盖范围单独报告。

## 独立消费者验收

- 在新 venv 从源码外导入，核对 scipy.linalg._fblas/_flapack 及其他 native module 的路径和依赖。
- 对固定正定/一般线性方程核对残差；对小型已知最优解的 linprog 问题检查可行性与目标值。
- 要求数值误差在声明容差内，不能仅以 import 成功作为交付。

## 交付物

- SciPy wheel、编译器/BLAS/ABI 清单。
- 官方模块测试报告、独立数值验收与动态库来源报告。

## 后续使用

下游应用加载该 wheel 求解新的边界条件或右端项，并保存结构化计算结果；延续原安装与 workspace。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：optional_frozen_functional_patch
- **patch_binding**：null
- **description**：主任务先完成 clean build。可选真实功能补丁必须由实例构建者绑定提交/patch 和独立验收后，再复用原构建树；未绑定时不生成修复步骤。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 CPU wheel + linalg 非 slow tests。

### Reference：正式参考配置

- **scope**：完整 CPU wheel + linalg/optimize 官方测试。

### Extended：扩展范围

- **scope**：增加 sparse/signal 等实际模块 tests；全套 slow/xslow 需要先独立准入。

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

- 预备 compiler runtimes、BLAS/LAPACK、pkg-config、NumPy 及构建/测试 wheels；源码 subprojects 一并固定。
- 目标 scipy wheel 不在初始环境；避免 editable import 自动重建把包加载时间混成安装验证。

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

- SciPy 主工程；BLAS/NumPy 与其他数值任务共享，Fortran/Pythran 编译路径体现新增工程行为。

## 与已有任务的关系

可能与旧 CPU/Memory/GPU 组共享软件来源；本次目标是构建、打包和验收工程产物。

## 范围说明

- planned_scale_class 是设计等级，尚未测得构建时间和内存/磁盘需求。
- 测试与产物容差以固定版本为准；不要求带时间戳的 wheel/archive 全字节相等。

## 官方来源

- [F_SP_BUILD] [SciPy build from source](https://docs.scipy.org/doc/scipy/building/) — 检查位置：Linux dependencies; source package build
- [F_SP_TEST] [Running SciPy tests locally](https://docs.scipy.org/doc/scipy/dev/contributor/devpy_test.html) — 检查位置：Selecting submodules and individual test cases
- [F_SP_PACKAGE] [SciPy pyproject](https://github.com/scipy/scipy/blob/main/pyproject.toml) — 检查位置：build-system; wheel/development test settings
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
