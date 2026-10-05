# BUILDv1-F10 · 构建 ONNX Runtime CPU wheel 与原生运行库

Build an ONNX Runtime CPU wheel and native runtime

**主工程**：[ONNX Runtime](https://github.com/microsoft/onnxruntime)  
**组别**：机器学习与数值计算框架　**规划规模**：大型　**实施优先级**：standard

**语言**：C++；C；Python  
**构建系统**：CMake；ONNX Runtime build.sh；Python wheel packaging  
**Canonical goal**：`build_install_verify_onnx_runtime_linux_cpu`

## Agent 任务目标

从源码交付具有 CPU execution provider 的 ONNX Runtime wheel 和共享库，通过官方运行时测试，并让独立进程加载与执行一个声明的 ONNX 模型。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 提供匹配源码的 submodules/deps archives、CMake/C++/Python、ONNX/protobuf 和小模型测试 fixtures；没有现成 ONNX Runtime package。

## 需要完成的工作

- 用官方 build.sh 编译共享库、Python binding 和 wheel。
- 运行固定 CPU runtime/provider/shared-lib 程序。
- 在新安装环境加载本地 ONNX 图，核对输入输出、线程运行和库来源。

## 目标范围

Linux CPU ONNX Runtime native library、Python binding/wheel、普通 CPU execution provider；默认非 minimal/operator-reduced build。

## 构建与测试入口

### Configure / Generate

- 固定 CPU build、CMake generator、BUILD_ROOT 和 Python ABI；不启用 CUDA/TensorRT/其他硬件 EP。

- 源码子模块与 FetchContent/deps 源在准备阶段完成；由 --skip_submodule_sync 防止任务期网络同步。

### Build

- ./build.sh --config Release --build_dir "$BUILD_ROOT" --build_shared_lib --build_wheel --parallel "$BUILD_JOBS" --skip_submodule_sync --update --build

### Package / Install

- 从本轮配置目录的 dist 选择准确 wheel；收集相同构建共享库与所需 license。

```bash
"$INSTALL_ROOT/bin/python" -m pip install --no-index --no-deps "$ARTIFACT_WHEEL"
```

### Official Tests

- 在 "$BUILD_ROOT/Release" 工作目录运行 ./onnxruntime_test_all 和 ./onnxruntime_shared_lib_test，并生成各自 gtest XML。

- reference 另运行 ./onnxruntime_provider_test；全部只编入声明 CPU EP，fixtures 按 build runner 布局预备。

## 官方测试选择

- **core**：onnxruntime_test_all + onnxruntime_shared_lib_test（官方 build.py 列明）。
- **reference**：增加 onnxruntime_provider_test；实际 test list 和配置产物共同冻结。
- **extended**：增加官方 Python API module 中 test_run_model2_contiguous / test_run_model_multiple_threads，或带独立 SDK 的额外 EP 编译。
- **rationale**：覆盖内核运行、图处理、provider 与 shared API；无需公开模型下载或训练。

## 独立消费者验收

- 新 venv 只安装本轮 wheel；检查 onnxruntime native pybind 模块及依赖路径。
- 加载冻结的小型 MatMul/Add/ReLU ONNX 图，用 CPUExecutionProvider 执行，对独立 NumPy 结果逐项校验。
- 新进程重载模型并测试另一合法输入；所用 op-set 与模型 hash 冻结。

## 交付物

- ONNX Runtime CPU wheel、共享库和依赖/EP 清单。
- 官方 C++ tests XML、编译日志、独立 ONNX 图消费报告。

## 后续使用

交付后应用加载新的兼容 ONNX 图并处理输入，验证安装包的图加载能力而非仅执行构建时缓存的一个输出。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：optional_frozen_functional_patch
- **patch_binding**：null
- **description**：主任务先完成 clean build。可选真实功能补丁必须由实例构建者绑定提交/patch 和独立验收后，再复用原构建树；未绑定时不生成修复步骤。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 CPU wheel/shared library + runtime/shared tests。

### Reference：正式参考配置

- **scope**：增加 CPU provider tests 与独立图加载运行。

### Extended：扩展范围

- **scope**：增加明确的 Python tests 或额外 CPU EP；GPU EP 只作具备 SDK/设备的能力扩展。

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

- 锁定 deps.txt/FetchContent/submodule 全部源码和 build/test wheels，预置 small ONNX fixtures。
- 预取 ONNX data 不等同于允许 runtime 官方二进制；目标 build cache 与安装均从空开始。

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

- ONNX Runtime 主工程；ONNX/protobuf/MLAS 是关联输入。
- 使用模型是很小的包可用性验收，与上一包大量任务侧推理不重复。

## 与已有任务的关系

可能与旧 CPU/Memory/GPU 组共享软件来源；本次目标是构建、打包和验收工程产物。

## 范围说明

- planned_scale_class 是设计等级，尚未测得构建时间和内存/磁盘需求。
- 测试与产物容差以固定版本为准；不要求带时间戳的 wheel/archive 全字节相等。

## 官方来源

- [F_ORT_BUILD] [ONNX Runtime inference build](https://onnxruntime.ai/docs/build/inferencing.html) — 检查位置：Linux; Common Build Instructions; Python build_wheel
- [F_ORT_RUNNER] [ONNX Runtime build/test orchestrator](https://github.com/microsoft/onnxruntime/blob/main/tools/ci_build/build.py) — 检查位置：run_onnxruntime_tests; build stages; wheel packaging
- [F_ORT_TEST] [ONNX Runtime Python tests](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/test/python/onnxruntime_test_python.py) — 检查位置：CPU Python API and ONNX fixture tests
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
