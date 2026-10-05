# BUILDv1-C08 · 构建 CPU 软件图形栈并验证离屏执行

Build a CPU software graphics stack and verify offscreen execution

**主工程**：[Mesa](https://gitlab.freedesktop.org/mesa/mesa)  
**组别**：多媒体、图形与地理计算工程　**规划规模**：大型　**实施优先级**：advanced

**语言**：C；C++；Python  
**构建系统**：Meson；Ninja  
**Canonical goal**：`engineering.build_install_test.mesa.linux_cpu`

## Agent 任务目标

为无物理 GPU 的 sandbox 构建可安装的 Mesa 软件图形库及 Vulkan ICD，交付能够执行离屏图形程序的 CPU 运行栈。

## 官方工作流与派生方式

Mesa 官方 Meson 构建 LLVMpipe/Lavapipe、utility 和 lp_test_*。

## 初始环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

## 需要完成的工作

- 配置 llvmpipe 与 swrast Vulkan 驱动，编译图形栈和单元测试。
- 安装本轮 EGL/GLES/driver/ICD 产物，运行软件渲染器测试与独立离屏应用。

## 目标范围

Linux LLVMpipe OpenGL/EGL/GLES 与 Lavapipe Vulkan CPU 软件实现；不使用实体 GPU 或 DRM render node 作为验收前提。

## 构建与测试入口

### Configure / Generate

```bash
meson setup "$BUILD_ROOT" "$SRC_ROOT" --prefix "$INSTALL_ROOT" --wrap-mode=nodownload -Dgallium-drivers=llvmpipe -Dvulkan-drivers=swrast -Dplatforms=[] -Dglx=disabled -Degl=enabled -Dllvm=enabled -Dbuild-tests=true
```

- LLVM、libdrm/headers、SPIR-V tools/headers 及 Python generators 使用冻结的声明依赖；安装库目录记录实际值。

### Build

```bash
meson compile -C "$BUILD_ROOT" -j "$BUILD_JOBS"
```

### Package / Install

```bash
meson install -C "$BUILD_ROOT"
```

- 保存实际 driver .so、EGL/GLES 库、Vulkan ICD JSON、开发 metadata 和相对/绝对加载路径。

### Official Tests

```bash
meson test -C "$BUILD_ROOT" --list
```

```bash
meson test -C "$BUILD_ROOT" util_tests process process_with_overrides lp_test_format lp_test_arit lp_test_blend lp_test_lerp lp_test_conv lp_test_printf --print-errorlogs
```

- reference 追加所选软件驱动自动注册的本地编译器/unit tests；测试名单冻结且要求非空。

## 官方测试选择

- **selectors**：util_tests；process；process_with_overrides；lp_test_format；lp_test_arit；lp_test_blend；lp_test_lerp；lp_test_conv；lp_test_printf
- **rationale**：覆盖生成代码、shader 算术/格式、进程和数据结构；外部离屏 consumer 补充实际驱动加载验证。

## 独立消费者验收

- 用本轮开发库编译 surfaceless EGL/pbuffer consumer，强制软件路径并绘制已知图案，读回像素检查。
- 显式设置 VK_DRIVER_FILES 到安装的 Lavapipe ICD，枚举本轮软件设备并执行固定 Vulkan compute/拷贝 consumer；记录真实 loader/driver 路径。

## 交付物

- Mesa 软件图形安装包
- Meson 配置、ICD/库清单
- 官方测试记录
- EGL 和 Vulkan consumer 及 readback 结果

## 后续使用

新进程使用同一安装包执行不同离屏 shader 和 readback，检验可复用加载状态与应用兼容性。

## 可选增量变化

- **enabled**：True
- **type**：optional_driver_enablement
- **delta**：在已有 LLVMpipe/Lavapipe 树中加入官方 zink 驱动构建。
- **acceptance**：在显式 Zink→Lavapipe CPU 链路上执行离屏 consumer，确认不是退回系统 OpenGL。

## 同一任务的规模配置

### Core：最小完整交付

LLVMpipe + EGL CPU 软件库、lp/utility tests 和 EGL consumer。

### Reference：正式参考配置

增加 Lavapipe Vulkan ICD、相应 unit tests 与 Vulkan consumer。

### Extended：扩展范围

加入 Zink 或冻结的更广泛上游软件驱动测试配置，额外 conformance harness 作为声明依赖。

## 可控变量

- 模块和测试范围随实例冻结；编译并行数 BUILD_JOBS 与测试并行数 TEST_JOBS 独立记录。
- 冷/热依赖缓存、ccache/sccache、优化等级和 clean/incremental 是场景变量，不增加任务 ID。

## 预期资源形态

- compiler_cpu
- linker_memory
- process_fanout
- filesystem_metadata
- build_workspace
- shader_codegen
- llvm_jit_validation

## 后端能力要求

- Linux x86_64；允许官方软件 renderer 的线程、共享库加载及 LLVM JIT 所需内存映射。
- EGL surfaceless/pbuffer 与 Vulkan loader 可用；验收必须实际加载本轮 CPU driver，无需物理 GPU、X server 或 root。

## 离线依赖准备

- 预置版本兼容的 LLVM、Meson/Ninja、Mako、Flex/Bison、SPIR-V 依赖和 GTest。
- Meson wraps 离线物化；图形测试数据和 shader 输入冻结。

## 回放与状态

- 依赖真实 configure、编译、链接、安装和测试完成事件；不能用记录的退出码或日志替代执行。
- 完整保留构建树、生成文件、测试临时目录和进程状态；退出码、测试结果及未完成工作都记录。

## 最终 oracle

- 独立核验源码标识、目标功能、安装清单及本轮构建来源。
- 报告测试发现/选择/实际执行/跳过/失败数；空套件或缺失强制测试不通过。
- 在源码树之外的干净 consumer 目录只使用本轮安装产物完成验收，排除系统预装版本。

## 应拒绝的负例

- 复制系统预装二进制冒充本轮构建。
- 修改筛选器使测试数为零或以大范围 skip 隐藏缺失功能。
- 安装包遗漏运行所需的动态库、插件、资源或开发文件。

## Builder 实施工作

- 固定可执行源码 revision、工具链和全部依赖摘要。
- 实现安装产物来源检查、非空测试清单和独立 consumer 验证器。
- 完成一次真实构建与回放，测量资源画像后确定资源规模标签。

## 源码血缘

- Mesa

## 与已有任务的关系

与 GPU 任务的设备执行不同，本任务源码构建并验收 CPU 软件图形实现；LLVM 为共享依赖，不重复计为独立来源。

## 范围说明

- 规模等级为设计预估；当前未构建或实测耗时、内存、I/O 与进程数量。
- 软件驱动通过不能推断任一硬件 GPU 驱动或完整 Khronos conformance 通过。

## 官方来源

- [C_MESA_BUILD] [Mesa compiling and installing](https://docs.mesa3d.org/install.html) — 检查位置：Meson build; local install; llvmpipe/swrast; installed-driver environment
- [C_MESA_OPTIONS] [Mesa Meson options](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/meson.options) — 检查位置：platforms, gallium-drivers, vulkan-drivers, glx, egl, llvm, build-tests
- [C_MESA_UTIL_TESTS] [Mesa utility test definitions](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/util/meson.build) — 检查位置：util_tests, process, process_with_overrides and util suite
- [C_MESA_LP_TESTS] [LLVMpipe test definitions](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/gallium/drivers/llvmpipe/meson.build) — 检查位置：lp_test_format, lp_test_arit, lp_test_blend, lp_test_lerp, lp_test_conv, lp_test_printf
- [C_MESA_LLVMPIPE] [Mesa LLVMpipe documentation](https://docs.mesa3d.org/drivers/llvmpipe.html) — 检查位置：Software rasterizer, LLVM requirement and tests

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
