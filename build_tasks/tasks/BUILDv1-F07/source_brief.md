# BUILDv1-F07 · 构建 pandas Cython 发行包并验收分组与时间索引

Build a pandas Cython distribution and verify grouping and time indexes

**主工程**：[pandas](https://github.com/pandas-dev/pandas)  
**组别**：机器学习与数值计算框架　**规划规模**：中型　**实施优先级**：pilot

**语言**：Python；Cython；C；C++  
**构建系统**：Meson；Ninja；meson-python；PEP 517  
**Canonical goal**：`build_install_verify_pandas_linux_cpu`

## Agent 任务目标

从源码编译 pandas 的底层扩展并交付 wheel，让独立应用可靠地处理带时间戳和缺失值的分组分析及索引操作。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 提供固定 NumPy、Cython/Meson/Ninja、Python、时区库和 pytest 依赖；pandas 未预装，源码版本 tags/metadata 已冻结。

## 需要完成的工作

- 通过 mesonpy 编译 native extensions，生成可独立安装的 wheel。
- 运行 libs/groupby/tslibs 对应官方 tests，报告明确的 skip。
- 使用新安装完成固定小表的分组、时间索引和文件重载核验。

## 目标范围

pandas wheel 的 Cython/native libs、时序和数据框接口；没有远程 SQL 服务或公开对象存储依赖。

## 构建与测试入口

### Configure / Generate

- 锁定 NumPy build ABI、Cython、mesonpy 和时区数据库版本；默认非 editable。

### Build

```bash
python -m build --wheel --no-isolation --outdir "$ARTIFACT_ROOT" "$SRC_ROOT"
```

- 保存本轮生成的 C/C++ 和 shared objects 的构建事件；增量 profile 才保留 build-dir。

### Package / Install

```bash
"$INSTALL_ROOT/bin/python" -m pip install --no-index --no-deps "$ARTIFACT_WHEEL"
```

### Official Tests

- core: python -m pytest --pyargs pandas.tests.libs pandas.tests.tslibs -m "not network and not db"

- reference: python -m pytest --pyargs pandas.tests.libs pandas.tests.tslibs pandas.tests.groupby -m "not network and not db"；所有普通数值案例实际执行。

## 官方测试选择

- **core**：官方 pandas.tests.libs 与 pandas.tests.tslibs。
- **reference**：再加入 pandas.tests.groupby；network/db markers 的排除在实例生成时冻结。
- **extended**：加入 pandas.tests.indexing 与固定 parser tests；外部数据库/网络集成不在 CPU baseline 中。
- **rationale**：官方指南明确区分 libs、tslibs、groupby；它们直接检验原生扩展及类型/缺失值语义。

## 独立消费者验收

- 检查 pandas._libs 下原生 .so 的来源属于本轮 wheel 安装；不能由源码树或 editable loader 导入。
- 固定含时区、缺失值和重复键的小表，独立核对 groupby 聚合、索引重排与输出 schema。
- 数据写出后新进程重载并检查类型与结果；验证不依赖安装目录外的原源码。

## 交付物

- pandas wheel、依赖/ABI/构建记录。
- 官方 libs/tslibs/groupby 测试报告和消费端数据工件。

## 后续使用

另一应用对追加的时间段使用同一安装和保存的数据重新聚合，检验交付后状态与类型语义。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：optional_frozen_functional_patch
- **patch_binding**：null
- **description**：主任务先完成 clean build。可选真实功能补丁必须由实例构建者绑定提交/patch 和独立验收后，再复用原构建树；未绑定时不生成修复步骤。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 pandas wheel + libs/tslibs tests。

### Reference：正式参考配置

- **scope**：完整 wheel + libs/tslibs/groupby tests。

### Extended：扩展范围

- **scope**：添加 indexing 和经过绑定的 parser tests；测试 worker 数变化是场景变量。

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

- 预取 pyproject/requirements 所需依赖与固定时区数据库；源码版本 metadata/tag 在运行前就绪。
- 不允许 pip 拉取公开 pandas wheel；测试数据位于冻结源码/fixtures，network/db 集成单独声明。

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

- pandas 主工程；与 Arrow/数据分析等先前任务运行时用途相关，本题只构建并验收库。

## 与已有任务的关系

可能与旧 CPU/Memory/GPU 组共享软件来源；本次目标是构建、打包和验收工程产物。

## 范围说明

- planned_scale_class 是设计等级，尚未测得构建时间和内存/磁盘需求。
- 测试与产物容差以固定版本为准；不要求带时间戳的 wheel/archive 全字节相等。

## 官方来源

- [F_PD_BUILD] [pandas build environment](https://pandas.pydata.org/docs/development/contributing_environment.html) — 检查位置：Step 3 build/install; Meson build directories
- [F_PD_TEST] [pandas test contribution guide](https://pandas.pydata.org/docs/development/contributing_codebase.html) — 检查位置：Test locations; Running test suite; network/db markers
- [F_PD_PACKAGE] [pandas pyproject](https://github.com/pandas-dev/pandas/blob/main/pyproject.toml) — 检查位置：build-system; optional-dependencies; license
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
