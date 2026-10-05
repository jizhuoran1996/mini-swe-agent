# BUILDv1-F02 · 从源码交付 TensorFlow CPU wheel 与可重载模型支持

Build a TensorFlow CPU wheel with SavedModel support

**主工程**：[TensorFlow](https://github.com/tensorflow/tensorflow)  
**组别**：机器学习与数值计算框架　**规划规模**：超大型　**实施优先级**：advanced

**语言**：Python；C；C++  
**构建系统**：Bazel；PEP 517 wheel target  
**Canonical goal**：`build_install_verify_tensorflow_linux_cpu`

## Agent 任务目标

从冻结 TensorFlow 源码交付 CPU Python 发行包，通过官方 softmax 和 SavedModel 测试，并让新进程加载交付环境中保存的计算图与变量。

## 官方工作流与派生方式

官方源码构建、发布包与本地测试工作流

## 初始环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 提供匹配 .bazelversion 的 Bazel、Clang、Python、完整 external repositories/工具链输入和 CPU 配置答案；没有目标 Bazel action cache。

## 需要完成的工作

- 根据固定 CPU 配置完成 Bazel wheel 构建。
- 执行已绑定的本地 kernel/SavedModel targets，保留 BEP/XML。
- 在新的安装环境真实导入 native TensorFlow、保存并重载一个固定小模型。

## 目标范围

完整 CPU Python TensorFlow wheel，包括本地产生的 native library 与 SavedModel；不要求 TensorFlow Serving、TPU/GPU kernels 或外部云服务。

## 构建与测试入口

### Configure / Generate

- 按 ./configure 的 CPU 答案冻结 .tf_configure.bazelrc、Python/Clang、目标 CPU flags；不启用 cuda/tpu。

- 源码检查与依赖 fetch 在计时前完成；Bazel server/output_base/action cache 是本轮新建。

- 实例保存一份共同 Bazel 基础配置，冻结源码、Python ABI、工具链、CPU 选项和 USE_PYWRAP_RULES 等 repository env；wheel 与 source tests 均使用该基线，test-specific linux 配置及任何差异另行声明和计量。

### Build

```bash
bazel build //tensorflow/tools/pip_package:wheel --repo_env=USE_PYWRAP_RULES=1 --repo_env=WHEEL_NAME=tensorflow_cpu --config=opt
```

### Package / Install

- 从 bazel-bin/tensorflow/tools/pip_package/wheel_house 选取与本轮 Python ABI 对应的唯一 wheel。

```bash
"$INSTALL_ROOT/bin/python" -m pip install --no-index --no-deps "$ARTIFACT_WHEEL"
```

### Official Tests

```bash
bazel test --config=linux //tensorflow/python/kernel_tests/nn_ops:softmax_op_test //tensorflow/python/saved_model:load_test
```

- core 可按官方 --test_filter=*LoadTest.test_capture_variables* 选择 load_test；reference 执行整个 load_test，冻结 CPU case 清单。

## 官方测试选择

- **core**：softmax_op_test 和 load_test 的 test_capture_variables 选择。
- **reference**：softmax_op_test 与完整 SavedModel load_test 两个已查阅官方 targets。
- **extended**：根据固定源码额外绑定 nn_ops 的本地 CPU targets；增加目标不得无声改变 reference。
- **rationale**：完整框架编译与有限但有意义的算子/状态恢复测试分离，避免整套分布式 CI 成为默认要求。

## 独立消费者验收

- 在不含源码路径的 venv 安装本轮 tensorflow_cpu wheel，核对 tensorflow 和其 native extension 路径/版本。
- 计算固定 softmax 与梯度；保存带变量的 tf.Module，关闭进程后从 SavedModel 恢复并核对结果。
- 核对 wheel CPU 标签、Bazel 构建信息和禁用的设备配置。
- 记录 tf.sysconfig.get_build_info() 并核对该 revision 的 CUDA/ROCm 构建标识，wheel 名称不能单独证明 CPU 配置。

## 交付物

- TensorFlow CPU wheel 与 build/test manifest。
- Bazel BEP、测试 XML、实际目标清单。
- 独立 SavedModel 保存/重载报告和输入产物。

## 后续使用

收到新的输入矩阵后在新进程加载已保存模型并计算结果，验证发行包在原构建进程结束后可使用。

## 可选增量变化

- **enabled_by_default**：False
- **mode**：optional_frozen_functional_patch
- **patch_binding**：null
- **description**：在主任务成功后，保留构建树应用与该版本配套的真实功能补丁；补丁及新增/回归验收由实例构建者先固定。未绑定补丁时只运行 clean baseline，不生成虚构修复任务。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 CPU wheel，加两个文档示范组件的有限测试。

### Reference：正式参考配置

- **scope**：完整 CPU wheel，加 softmax 和 SavedModel load 全套本地测试。

### Extended：扩展范围

- **scope**：增加经过离线准入的 CPU 算子测试或独立 CUDA wheel 编译配置；扩展不代表新 task。

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

- 固定 Bazel module/repository cache、protobuf、XLA/LLVM、Python wheels、编译器和测试 fixtures。
- 允许预取 external 源码与工具；禁用 remote action-cache 命中目标输出，不使用已有 tensorflow wheel 替代目标。

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
- 将示例 build/test 命令解析为共享基础配置的固定命令；源码测试可能产生额外编译，不能当作直接验证 wheel native library 身份。

## 源码血缘

- TensorFlow 主工程；Bazel external XLA/LLVM 与 JAX 任务共享部分依赖。
- 遵循当前官方 wheel target；老版 build_pip_package 指令不能直接与当前 main 配置混用。

## 与已有任务的关系

与此前 CPU/内存/GPU 运行任务可能使用同一库；本任务的交付目标是从源码构建、安装并验证该工程。

## 范围说明

- 规模等级为设计选择，尚无本包实测的构建时间、内存或磁盘结论。
- 不以 wheel/归档字节完全一致作为默认正确性条件；构建 ID 和时间戳单独记录。

## 官方来源

- [F_TF_BUILD] [TensorFlow build from source](https://www.tensorflow.org/install/source) — 检查位置：Build the package; CPU wheel; configuration
- [F_TF_TEST] [TensorFlow contribution guide](https://github.com/tensorflow/tensorflow/blob/master/CONTRIBUTING.md) — 检查位置：Running unit tests; softmax_op_test; SavedModel load_test
- [F_PYPA_BUILD] [PyPA build frontend](https://build.pypa.io/en/stable/reference/cli.html) — 检查位置：CLI: wheel and no-isolation options

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
