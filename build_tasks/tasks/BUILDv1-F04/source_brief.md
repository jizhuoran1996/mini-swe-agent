# BUILDv1-F04 · 构建 scikit-learn 原生扩展发行包并验证邻域搜索与模型流水线

Build scikit-learn native extensions and verify model pipelines

**主工程**：[scikit-learn](https://github.com/scikit-learn/scikit-learn)  
**组别**：机器学习与数值计算框架　**规划规模**：中型　**实施优先级**：pilot

**语言**：Python；Cython；C；C++  
**构建系统**：Meson；Ninja；meson-python；PEP 517  
**Canonical goal**：`build_install_verify_scikit_learn_linux_cpu`

## Agent 任务目标

从源码构建包含原生树和数值扩展的 scikit-learn wheel，供下游应用完成邻域查询与可重载的分类流水线。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 固定 NumPy/SciPy ABI 依赖、Cython/Meson/Ninja、OpenMP 与测试依赖；这些依赖可预装，scikit-learn 本身必须未构建。

## 需要完成的工作

- 编译整个所选 scikit-learn wheel，保留 Cython→C/C++→shared object 的日志。
- 验证官方邻域树测试，reference 扩展到完整 neighbors tests。
- 在新消费端进行邻域查询和 Pipeline fit/predict/序列化重载。

## 目标范围

Linux CPU scikit-learn wheel，包含 Cython/native extensions；不是仅 Python metadata wheel，也不是重建其已固定 NumPy/SciPy 依赖。

## 构建与测试入口

### Configure / Generate

- 固定 mesonpy backend 与 pyproject build requirements；声明 OpenMP runtime 和 NumPy ABI。

### Build

```bash
python -m build --wheel --no-isolation --outdir "$ARTIFACT_ROOT" "$SRC_ROOT"
```

- 如需保留构建树，使用固定 Meson-Python 版本的 build-dir 配置；编译并发通过 compile-args 控制。

### Package / Install

```bash
"$INSTALL_ROOT/bin/python" -m pip install --no-index --no-deps "$ARTIFACT_WHEEL"
```

### Official Tests

- 在新环境从源码外运行 python -m pytest --pyargs sklearn.neighbors.tests.test_kd_tree --import-mode=importlib

- reference: python -m pytest --pyargs sklearn.neighbors.tests --import-mode=importlib；测试依赖及原始 fixtures 全部预载。

## 官方测试选择

- **core**：官方 sklearn/neighbors/tests/test_kd_tree.py。
- **reference**：官方 sklearn.neighbors.tests 子包；先固定 collect-only 清单，报告完整结果。
- **extended**：扩展官方 model_selection/test_search.py 与 tree/ensemble 本地 suites，绑定版本对应清单后启用。
- **rationale**：核心测试直接消费编译后的 KD/Ball tree 扩展；独立流水线检查 Python 与原生层整合。

## 独立消费者验收

- 检查 sklearn 和 sklearn.neighbors._kd_tree 真实路径属于本轮 wheel 安装。
- 在固定离线小数据上比较 KDTree 查询与独立穷举距离排序。
- 构建 StandardScaler+分类器 Pipeline，保存后新进程加载并核对预测。

## 交付物

- 本轮 scikit-learn wheel 和 native extension/依赖清单。
- 邻域测试报告、消费端查询/预测结果及可重载对象。

## 后续使用

新应用加载已经交付的 Pipeline，对新增行完成预测；如另做增量构建，必须先固定真实源码补丁。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：optional_frozen_functional_patch
- **patch_binding**：null
- **description**：在主任务成功后，保留构建树应用与该版本配套的真实功能补丁；补丁及新增/回归验收由实例构建者先固定。未绑定补丁时只运行 clean baseline，不生成虚构修复任务。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 wheel + KDTree 官方测试。

### Reference：正式参考配置

- **scope**：完整 wheel + neighbors 本地套件与下游流水线验收。

### Extended：扩展范围

- **scope**：添加已绑定的 model_selection/tree/ensemble 官方 suites；线程或编译优化变化仍为同一任务变体。

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

- 锁定 Cython、meson-python、Ninja、NumPy/SciPy、joblib/threadpoolctl、hypothesis/pytest 所需 wheels。
- 不允许 pip 下载 scikit-learn 或使用已有 editable loader；测试不调用 fetch_* 公共数据下载。

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

- scikit-learn；共享 NumPy/SciPy/OpenMP 依赖，工具链大体属于 Meson/Cython 家族。

## 与已有任务的关系

与此前 CPU/内存/GPU 运行任务可能使用同一库；本任务的交付目标是从源码构建、安装并验证该工程。

## 范围说明

- 规模等级为设计选择，尚无本包实测的构建时间、内存或磁盘结论。
- 不以 wheel/归档字节完全一致作为默认正确性条件；构建 ID 和时间戳单独记录。

## 官方来源

- [F_SK_BUILD] [scikit-learn development setup](https://scikit-learn.org/stable/developers/development_setup.html) — 检查位置：Linux; editable build; testing
- [F_SK_PACKAGE] [scikit-learn pyproject](https://github.com/scikit-learn/scikit-learn/blob/main/pyproject.toml) — 检查位置：build-system; pytest testpaths and import mode
- [F_SK_TEST] [scikit-learn KD-tree tests](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/neighbors/tests/test_kd_tree.py) — 检查位置：KDTree official test module
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
