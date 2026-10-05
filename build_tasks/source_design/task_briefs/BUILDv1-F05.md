# BUILDv1-F05 · 编译 NumPy 数组运行时及开发接口发行包

Build the NumPy array runtime and development interfaces

**主工程**：[NumPy](https://github.com/numpy/numpy)  
**组别**：机器学习与数值计算框架　**规划规模**：中型　**实施优先级**：pilot

**语言**：Python；C；C++；Cython  
**构建系统**：Meson；Ninja；meson-python；PEP 517  
**Canonical goal**：`build_install_verify_numpy_linux_cpu`

## Agent 任务目标

从源码交付 NumPy wheel，包含数组/ufunc 原生扩展、线性代数与随机模块，以及可供下游扩展使用的开发头文件。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 预装固定 C/C++ 编译器、Python headers、Cython、Meson 和选定 OpenBLAS/LAPACK；NumPy wheel 和其目标缓存为空。

## 需要完成的工作

- 配置所需 BLAS/CPU dispatch 并编译完整 NumPy wheel。
- 从安装环境执行官方数值测试。
- 检验矩阵、FFT/随机对象和数组持久化；扩展 profile 可验证 C API/F2PY。

## 目标范围

完整 CPU NumPy wheel 及头文件、原生模块。reference 官方非 slow suite 已明确排除慢例，不以本轮失败情况动态删例。

## 构建与测试入口

### Configure / Generate

- 冻结 BLAS/LAPACK 实现、LP64/ILP64、CPU baseline/dispatch 与工具链；reference 要求有声明的 BLAS，禁止无声退回 no-BLAS。

### Build

```bash
python -m build --wheel --no-isolation --outdir "$ARTIFACT_ROOT" "$SRC_ROOT"
```

### Package / Install

```bash
"$INSTALL_ROOT/bin/python" -m pip install --no-index --no-deps "$ARTIFACT_WHEEL"
```

- 保留 wheel 中的 runtime、tests、devel 安装项；核查 numpy-config/headers 与实际 native libraries。

### Official Tests

- core: python -m pytest --pyargs numpy.linalg -m "not slow"

- reference: python -m pytest --pyargs numpy -m "not slow"；使用官方 requirements/test_requirements 和记录的测试资源边界。

## 官方测试选择

- **core**：numpy.linalg 的官方非 slow tests。
- **reference**：NumPy wheel CI 使用的 --pyargs numpy -m 'not slow' 形式；固定支持平台清单。
- **extended**：增加 slow tests 的已准入选择与原生 C API/F2PY 消费端构建，若用 Fortran 则单独声明工具链。
- **rationale**：覆盖数组语义、BLAS 数值路径、packaging 和开发文件，构建规模不靠重复运行小矩阵扩大。

## 独立消费者验收

- 确认 numpy._core._multiarray_umath、BLAS 动态依赖和头文件均来自交付路径/已声明依赖。
- 固定矩阵求解检查残差、FFT 往返误差、随机种子输出及 .npy 新进程重载。
- extended 新编译一个使用 NumPy C API 的小模块；检查头文件来自本轮 numpy.get_include()。

## 交付物

- NumPy wheel、BLAS/CPU 配置和原生扩展清单。
- 官方测试报告与独立数值/持久化检查。

## 后续使用

下游使用交付头文件和数组 API 编译一个小 C 扩展，并处理新增数组输入；这部分单独记录为消费验证成本。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：optional_frozen_functional_patch
- **patch_binding**：null
- **description**：在主任务成功后，保留构建树应用与该版本配套的真实功能补丁；补丁及新增/回归验收由实例构建者先固定。未绑定补丁时只运行 clean baseline，不生成虚构修复任务。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 wheel + linalg 基础测试。

### Reference：正式参考配置

- **scope**：完整 wheel + 官方非 slow 数值测试集。

### Extended：扩展范围

- **scope**：经过准入的 slow、C API 和 F2PY tests；不改变 task identity。

## 可控变量

- 冻结编译并发与测试并发；CPU/内存限额独立记录。
- 编译缓存关闭为默认；依赖下载缓存只保存源码/工具，不保存目标对象和目标 wheel。
- OpenMP/BLAS 线程数、CPU 指令集与链接策略写入实例；等待期间已启动子进程继续计量。

## 预期资源形态

- compiler_cpu
- linker_memory
- process_creation
- filesystem_metadata
- build_workspace
- test_subprocesses

## 后端能力要求

- Linux x86_64、普通用户可执行编译器/链接器与 Python 子进程。
- 可写工作盘、可用共享内存/线程；不要求 GPU、root、外部集群或构建阶段访问 Internet。

## 离线依赖准备

- 预取固定 submodules/vendored Meson、Python build/test wheels、OpenBLAS 头文件/共享库及 pkg-config 元数据。
- 不从 PyPI 拉取目标 numpy wheel；只使用预备依赖且独立安装防止旧 numpy 引入。

## 回放与状态

- 依赖 configure→compile/link→package→install→test 的真实完成事件；进程退出和测试状态由当次运行产生。
- 冻结源码、依赖、配置、测试清单与路径角色；不复用记录 PID，也不把旧安装或旧日志当成本轮输出。

## 最终 oracle

- 确认目标来源、构建日志与产物相符；在新消费环境检查包和 native extension 的实际载入路径。
- 冻结选定测试清单并报告 collected/selected/executed/skipped/failed；空套件、预先全部跳过或错误目标不算通过。

## 应拒绝的负例

- 替换为预装发行 wheel、导入源码树或漏装 native extension 应被拒绝。
- 仅产生日志/metadata 而未完成原生编译，或漏跑已声明的官方测试应被拒绝。

## Builder 实施工作

- 绑定兼容的源码提交、工具链/依赖版本和不可变资产 hash。
- 编写构建/测试事件采集器和独立消费端验收，完成参考机器上的首次准入。

## 源码血缘

- NumPy 主工程；可作为本组其他项目的预装依赖，但它们的构建任务不重复计费 NumPy 源码编译。

## 与已有任务的关系

与此前 CPU/内存/GPU 运行任务可能使用同一库；本任务的交付目标是从源码构建、安装并验证该工程。

## 范围说明

- 规模等级为设计选择，尚无本包实测的构建时间、内存或磁盘结论。
- 不以 wheel/归档字节完全一致作为默认正确性条件；构建 ID 和时间戳单独记录。

## 官方来源

- [F_NP_BUILD] [NumPy build from source](https://numpy.org/devdocs/building/) — 检查位置：Building NumPy; dependencies; pip source builds
- [F_NP_PACKAGE] [NumPy pyproject and wheel testing](https://raw.githubusercontent.com/numpy/numpy/main/pyproject.toml) — 检查位置：build-system; cibuildwheel; Meson install tags
- [F_NP_TEST] [NumPy test environment](https://numpy.org/devdocs/dev/development_environment.html) — 检查位置：Testing; spin; f2py script test example
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
