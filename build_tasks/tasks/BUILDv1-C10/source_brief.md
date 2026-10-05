# BUILDv1-C10 · 构建支持 CPU 离屏可视化的科学 SDK

Build a scientific SDK with CPU offscreen visualization

**主工程**：[VTK](https://gitlab.kitware.com/vtk/vtk)  
**组别**：多媒体、图形与地理计算工程　**规划规模**：超大型　**实施优先级**：advanced

**语言**：C++；C；Python  
**构建系统**：CMake；Ninja  
**Canonical goal**：`engineering.build_install_test.vtk.linux_cpu`

## Agent 任务目标

交付可被第三方 C++ 工程使用的科学数据、几何和可视化 SDK，支持读写 XML 数据与 CPU 离屏绘图；验证安装后模块依赖和渲染路径。

## 官方工作流与派生方式

VTK 原生 CMake SDK 构建、模块 C++ tests 与 EGL/offscreen tests。

## 初始环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

## 需要完成的工作

- 构建明确的 Common/Filters/IO 模块及 reference 中的 RenderingOpenGL2。
- 安装完整 SDK，运行数据/过滤器/文件格式回归和真实 CPU EGL rendering tests。

## 目标范围

Linux CPU 数据/几何/I/O SDK 与 reference 的 Mesa EGL 离屏渲染；明确无 MPI、Qt、物理 GPU 条件。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -G Ninja -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DCMAKE_BUILD_TYPE=Release -DVTK_INSTALL_SDK=ON -DVTK_BUILD_TESTING=WANT -DVTK_USE_MPI=OFF -DVTK_WRAP_PYTHON=OFF -DVTK_USE_X=OFF -DVTK_OPENGL_HAS_EGL=ON -DVTK_USE_MESA_SOFTWARE_RENDERING=ON -DVTK_DEFAULT_RENDER_WINDOW_HEADLESS=ON
```

- 模块配置使用 VTK_MODULE_ENABLE_VTK_<Module>=YES：CommonCore、CommonDataModel、FiltersCore、FiltersGeneral、IOLegacy、IOXML；reference 增加 RenderingCore、RenderingOpenGL2、FiltersSources。对非目标组按上游 mini preset 设 DONT_WANT，Qt/Web 为 NO，关闭 MPI；根据源码模块/测试依赖解析并冻结最终列表。

- 将 ExternalData 对象和 image baselines 预置并锁定；WANT 允许不相关能力缺席，但以下强制测试必须构建和执行。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 归档共享库、头文件、VTKConfig.cmake、模块依赖信息和必要运行资源。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -N
```

- 运行源定义中 vtkCommonCoreCxxTests 对应的 TestArray*、TestSmartPointer、TestNew；vtkFiltersCoreCxxTests 的 TestCleanPolyData、TestThreshold；vtkIOXMLCxxTests 的 TestXMLWriteRead。

- reference 必须执行 TestOffscreenRenderingResize 和 EGL 条件下的 TestEGLRenderWindowResize；从该 revision 的 CTest 名称清单冻结完整名称。

## 官方测试选择

- **sources**：Common/Core/Testing/Cxx/CMakeLists.txt；Filters/Core/Testing/Cxx/CMakeLists.txt；IO/XML/Testing/Cxx/CMakeLists.txt；Rendering/OpenGL2/Testing/Cxx/CMakeLists.txt
- **mandatory_cases**：TestArrayAPI；TestSmartPointer；TestNew；TestCleanPolyData；TestThreshold；TestXMLWriteRead；TestOffscreenRenderingResize；TestEGLRenderWindowResize
- **rationale**：验证大型模板/模块工程、引用计数、数据管线、序列化和实际离屏 context；不能只通过无渲染单元测试宣称 reference 完成。

## 独立消费者验收

- 独立 CMake consumer 显式 find_package(VTK COMPONENTS ...) 并调用 vtk_module_autoinit，链接本轮安装 SDK。
- 读取固定网格、执行过滤器、保存/重载 XML，再通过显式 CPU EGL render window 绘制并检查像素和数值；确认实际 renderer 为软件实现。

## 交付物

- 科学 SDK 安装包
- 模块/依赖/Mesa/EGL 配置清单
- CTest 与图像比较结果
- 独立 consumer、网格和截图产物

## 后续使用

为 consumer 加入另一种过滤器并重新编译运行，复用原 SDK 与上轮 XML 产物，验证安装包开发接口完整。

## 可选增量变化

- **enabled**：True
- **type**：optional_module_enablement
- **delta**：在已有构建中加入一个已预置依赖、带官方测试的真实 IO 模块。
- **module_binding**：实施时固定具体模块、其源内 CMake option 和 consumer 格式要求。
- **acceptance**：新增模块的官方 tests 与外部读写 consumer 通过；基线任务不依赖此可选变体。

## 同一任务的规模配置

### Core：最小完整交付

Common/Filters/IO 多模块 SDK 与非渲染 C++ test suites。

### Reference：正式参考配置

加入 RenderingOpenGL2 和真实 Mesa CPU EGL 离屏验证；强制测试清单齐全。

### Extended：扩展范围

扩大科学 IO/过滤器模块，或构建 Python wrappers 并运行对应官方 tests；额外大数据 fixtures 预置。

## 可控变量

- 模块和测试范围随实例冻结；编译并行数 BUILD_JOBS 与测试并行数 TEST_JOBS 独立记录。
- 冷/热依赖缓存、ccache/sccache、优化等级和 clean/incremental 是场景变量，不增加任务 ID。

## 预期资源形态

- compiler_cpu
- linker_memory
- process_fanout
- filesystem_metadata
- build_workspace
- template_heavy_cxx
- multi_library_link
- offscreen_validation

## 后端能力要求

- Linux x86_64、C++ 工具链及足够私有构建空间。
- reference 需要可实际初始化的 Mesa CPU EGL context；不需要物理 GPU/X server，能力缺失应阻止该 profile 准入。

## 离线依赖准备

- 固定 VTK、CMake/Ninja、XML/压缩/科学格式依赖、测试工具和预构建 Mesa 软件 EGL。
- CMake ExternalData object store 和参考图像按哈希预置；构建测试不能在线补数据。

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

- VTK

## 与已有任务的关系

与科学/GPU应用可能共享 VTK；本任务验收原生科学 SDK 构建，不按渲染循环制造资源规模。

## 范围说明

- 规模等级为设计预估；当前未构建或实测耗时、内存、I/O 与进程数量。
- 不同 VTK release 的 EGL/Mesa option 支持需与所选 revision 对齐；数据-only core 和带渲染 reference 是明确不同 profile。

## 官方来源

- [C_VTK_BUILD] [Building VTK](https://docs.vtk.org/en/latest/build_instructions/build.html) — 检查位置：Sources, optional dependencies, out-of-tree CMake configure/build
- [C_VTK_CONFIG] [VTK build settings](https://docs.vtk.org/en/latest/build_instructions/build_settings.html) — 检查位置：VTK_BUILD_TESTING; SDK; EGL/headless; MESA software rendering
- [C_VTK_CORE_TESTS] [VTK CommonCore C++ tests](https://github.com/Kitware/VTK/blob/master/Common/Core/Testing/Cxx/CMakeLists.txt) — 检查位置：vtkCommonCoreCxxTests; TestArray*, TestSmartPointer, TestNew
- [C_VTK_FILTER_TESTS] [VTK FiltersCore C++ tests](https://github.com/Kitware/VTK/blob/master/Filters/Core/Testing/Cxx/CMakeLists.txt) — 检查位置：vtkFiltersCoreCxxTests; TestCleanPolyData*, TestThreshold*
- [C_VTK_XML_TESTS] [VTK IOXML C++ tests](https://github.com/Kitware/VTK/blob/master/IO/XML/Testing/Cxx/CMakeLists.txt) — 检查位置：vtkIOXMLCxxTests, TestXMLWriteRead and TestXMLCInterface
- [C_VTK_GL_TESTS] [VTK OpenGL2 C++ tests](https://github.com/Kitware/VTK/blob/master/Rendering/OpenGL2/Testing/Cxx/CMakeLists.txt) — 检查位置：TestOffscreenRenderingResize and EGL-gated TestEGLRenderWindowResize
- [C_VTK_MODULE_CONFIG] [VTK module selection implementation](https://github.com/Kitware/VTK/blob/master/CMake/vtkModule.cmake) — 检查位置：vtk_module_scan and VTK_MODULE_ENABLE_/VTK_GROUP_ENABLE_ configuration states

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
