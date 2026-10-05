# BUILDv1-F01 · 构建并交付 CPU PyTorch 发行包及扩展开发环境

Build a CPU PyTorch distribution and extension SDK

**主工程**：[PyTorch](https://github.com/pytorch/pytorch)  
**组别**：机器学习与数值计算框架　**规划规模**：超大型　**实施优先级**：advanced

**语言**：Python；C；C++  
**构建系统**：CMake；Ninja；scikit-build-core；PEP 517  
**Canonical goal**：`build_install_verify_pytorch_linux_cpu`

## Agent 任务目标

从提供的 PyTorch 源码交付 CPU wheel，证明其张量运算、自动求导、序列化和 C++ 扩展接口可用于新的应用。主任务完整构建 CPU 框架，不需要训练大模型。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 依赖包含 Python、C++20 编译器、CMake/Ninja、所选 BLAS/OpenMP、scikit-build-core 与测试组；源码 submodules 已就绪。BUILD_ROOT 对应固定的 CMake build-dir。
- 对已检查的 main 配方固定 BUILD_ROOT=SRC_ROOT/build；若覆盖 scikit-build build-dir 则将该参数写入唯一实例配置。

## 需要完成的工作

- 核对 CPU-only 配置并生成真实 ATen/torchgen 与 native libraries。
- 构建 wheel，安装到独立 venv；运行指定 PyTorch 官方测试。
- 由新消费端做张量/梯度/保存重载检查，随后从同一 wheel 的头文件编译一个小扩展。

## 目标范围

Linux x86_64 CPU wheel：ATen、autograd、torch.nn、序列化和 C++ extension headers；reference 包含其普通 CPU kernels，不启用 GPU toolchain。

## 构建与测试入口

### Configure / Generate

- 固定 USE_CUDA=0、USE_ROCM=0、USE_XPU=0；reference 保留官方 CPU backend 默认功能。

- 冻结 MAX_JOBS 或 CMAKE_BUILD_PARALLEL_LEVEL；当已有 CMakeCache 时不假定修改环境变量会覆盖旧值。

### Build

```bash
python -m build --wheel --no-isolation --outdir "$ARTIFACT_ROOT" "$SRC_ROOT"
```

- PEP 517 调用已查阅 main 的 scikit-build-core/CMake；若固定旧 release，必须采用该 release 的 backend，不混用 main 配方。

### Package / Install

```bash
"$INSTALL_ROOT/bin/python" -m pip install --no-index --no-deps "$ARTIFACT_WHEEL"
```

- 记录 torch 与 torch._C 的文件路径、wheel RECORD 和 torch.__config__.show()。

### Official Tests

- 在源码目录外运行该 wheel 环境的 python -m pytest "$SRC_ROOT/test/test_nn.py" -k Linear --import-mode=importlib

- reference 另运行 "$SRC_ROOT/test/test_autograd.py" 的 CPU 套件；按固定版本冻结收集结果、测试依赖和预期 CPU skips。

## 官方测试选择

- **core**：test/test_nn.py 中 -k Linear 的官方选择。
- **reference**：上述选择加 test/test_autograd.py；全部依赖离线提供，GPU-only cases 的预期 skip 随清单固定。
- **extended**：增加 test/test_nn.py 完整 CPU 选择和匹配版本的官方 CPU C++ test targets；不宣称通过完整异构 CI。
- **rationale**：同时覆盖原生张量内核、Python binding 和反向传播；wheel 完整编译，验收不依赖下载模型。

## 独立消费者验收

- 从 SRC_ROOT 外安装本轮 wheel，assert torch._C 路径处于 INSTALL_ROOT，检查版本/构建配置与 manifest。
- 比较固定小矩阵运算及解析梯度，保存 state_dict 后新进程重载。
- 用 torch.utils.cpp_extension 和交付 headers 构建固定 C++ 张量加法扩展，核对实际加载的扩展路径与输出。
- C++ extension consumer 显式指定独立且初始为空的 session-scoped build_directory；新扩展编译、加载与 grader 成本单独记录，不使用历史 TORCH_EXTENSIONS_DIR 对象缓存。

## 交付物

- CPU torch wheel、构建配置与动态库清单。
- 官方测试报告及独立消费端/扩展构建报告。
- 保留的构建树引用、源依赖锁和产物 hash。

## 后续使用

交付后收到一个使用 torch C++ API 的小扩展源码，为新应用编译并验证该扩展；消费本轮 SDK，不重装公开 wheel。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：optional_frozen_functional_patch
- **patch_binding**：null
- **description**：在主任务成功后，保留构建树应用与该版本配套的真实功能补丁；补丁及新增/回归验收由实例构建者先固定。未绑定补丁时只运行 clean baseline，不生成虚构修复任务。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：CPU wheel，按官方选项关闭 distributed 和未需要的 CPU 加速 backend；执行 Linear 验收。

### Reference：正式参考配置

- **scope**：完整常用 CPU wheel，保留 CPU backend 与 autograd；执行声明的两组测试。

### Extended：扩展范围

- **scope**：增加官方 C++ CPU tests 或独立 GPU SDK 编译 profile；GPU profile 单独准入且需要设备才能声称 GPU 运行通过。

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

- 冻结 submodule commit、torchgen 依赖、BLAS/OpenMP 和 pyproject 所需 build/test wheels。
- 将工具与依赖 wheelhouse 预装；移除目标 torch wheel 和目标对象缓存，记录是否使用 CPU assembly/codegen。

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

- PyTorch 主仓库和固定 submodules；与本套 LLVM/NumPy 等任务有工具或依赖共享。
- 此前 GPU pack 使用 PyTorch 执行训练/推理；这里只将训练样例用于小型产物验证。

## 与已有任务的关系

与此前 CPU/内存/GPU 运行任务可能使用同一库；本任务的交付目标是从源码构建、安装并验证该工程。

## 范围说明

- 规模等级为设计选择，尚无本包实测的构建时间、内存或磁盘结论。
- 不以 wheel/归档字节完全一致作为默认正确性条件；构建 ID 和时间戳单独记录。

## 官方来源

- [F_PT_README] [PyTorch source installation](https://github.com/pytorch/pytorch/blob/main/README.md) — 检查位置：From Source; CPU accelerator-disable variables; prerequisites
- [F_PT_BUILD] [PyTorch pyproject build backend](https://github.com/pytorch/pytorch/blob/main/pyproject.toml) — 检查位置：build-system; tool.scikit-build; MAX_JOBS forwarding
- [F_PT_TEST] [PyTorch contribution and testing guide](https://raw.githubusercontent.com/pytorch/pytorch/main/CONTRIBUTING.md) — 检查位置：Testing; Python Unit Testing; build options
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
