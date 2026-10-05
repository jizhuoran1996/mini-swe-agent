# BUILDv1-C06 · 构建无界面的 Blender 场景处理与 CPU 渲染发行包

Build a headless Blender distribution for scene processing and CPU rendering

**主工程**：[Blender](https://projects.blender.org/blender/blender)  
**组别**：多媒体、图形与地理计算工程　**规划规模**：超大型　**实施优先级**：advanced

**语言**：C；C++；Python  
**构建系统**：CMake；Ninja  
**Canonical goal**：`engineering.build_install_test.blender.linux_cpu`

## Agent 任务目标

为渲染 worker 从源码构建 Blender，交付包含 Python 运行时和所需资源的 headless 发行目录；验证几何编辑、blend 文件读写及 CPU Cycles 渲染。

## 官方工作流与派生方式

Blender 官方 headless CMake preset、GTest、Python 几何/文件及 Cycles CPU regression 流程。

## 初始环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。
- 与源码匹配的 Blender tests/files 数据树已完整物化；所需 OpenImageIO oiiotool 与 CPU Cycles 依赖可用。

## 需要完成的工作

- 使用官方 headless preset 配置完整 Blender，启用测试和 CPU Cycles。
- 编译链接大型应用及测试、完成安装，执行明确的无 GUI regression，并从安装目录运行外部脚本。

## 目标范围

完整 Linux headless Blender，几何/文件 API 和 CPU Cycles；headless preset 关闭音频/视频等特定功能，目标清单照实际 preset 冻结。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -G Ninja -C "$SRC_ROOT/build_files/cmake/config/blender_headless.cmake" -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DWITH_GTESTS=ON -DWITH_CYCLES=ON -DCYCLES_TEST_DEVICES=CPU -DWITH_CYCLES_DEVICE_CUDA=OFF -DWITH_CYCLES_DEVICE_OPTIX=OFF -DWITH_CYCLES_DEVICE_HIP=OFF -DWITH_CYCLES_DEVICE_ONEAPI=OFF -DWITH_CYCLES_CUDA_BINARIES=OFF -DWITH_CYCLES_HIP_BINARIES=OFF -DWITH_GPU_RENDER_TESTS=OFF -DWITH_GPU_COMPOSITOR_TESTS=OFF
```

- 绑定官方已预置 library bundle；测试数据放在该 revision 的 SRC_ROOT/tests/files，并显式解析 OPENIMAGEIO_TOOL 到锁定的 oiiotool；缺少样本或工具导致目标测试未注册时，实例准备失败。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --build "$BUILD_ROOT" --target install
```

- 归档 Blender 可执行文件、Python runtime、启动脚本、动态库与必要数据目录。

### Official Tests

```bash
ctest --test-dir "$BUILD_ROOT" -N
```

- ctest --test-dir "$BUILD_ROOT" -R "^(bmesh_bevel|bmesh_boolean|mesh_join|mesh_validate|blendfile_liblink|blendfile_relationships|cycles_mesh_cpu)$" --output-on-failure；这些名称来自源中 add_blender_test 和 cycles_<group>_<device> 注册。

- 另执行从本 revision CTest 清单冻结的非 GPU C/C++ GTest 选择；更广的 CPU render groups 使用同一 tests/files 基线和上游图像比较规则。

## 官方测试选择

- **selectors**：bmesh_bevel；bmesh_boolean；mesh_join；mesh_validate；blendfile_liblink；blendfile_relationships；cycles_mesh_cpu
- **gtest_policy**：从该 revision 的 CTest 清单冻结非 GPU C/C++ tests，不能用无测试构建替代。
- **rationale**：大型 C/C++/Python 工程同时检验工具链接、嵌入式解释器、场景状态和真实软件渲染。

## 独立消费者验收

- 在安装树之外通过 blender --background --factory-startup --python 执行固定脚本，读取场景、修改几何并另存 blend。
- 由第二次独立 Blender 进程重新加载产物，验证对象/网格属性并以 CPU Cycles 输出一帧，按固定容差检查图像。

## 交付物

- 可执行 headless 发行目录归档
- 源/依赖/preset 和 CPU device 清单
- CTest 和 render-test 报告
- 外部场景脚本、blend 与验证帧

## 后续使用

用已安装应用加载上一轮 blend，修改材质或几何再输出第二个场景与渲染，检验持续 workspace 与产物兼容性。

## 可选增量变化

- **enabled**：True
- **type**：optional_frozen_upstream_patch
- **delta**：可选择一个对当前 revision 适用的真实 Blender 功能修复，保留构建树重新编译。
- **patch_binding**：实施时绑定具体上游 patch/commit 与对应 regression；本任务默认不依赖该变体。
- **acceptance**：对应 regression 和原有场景 consumer 均通过；记录实际重新生成的对象与链接步骤。

## 同一任务的规模配置

### Core：最小完整交付

官方 headless 完整应用、C/C++ 与几何/文件测试；只选择有限官方 render group。

### Reference：正式参考配置

完整 CPU Cycles headless 发行包以及冻结几何、文件和 CPU 渲染组。

### Extended：扩展范围

启用额外官方 CPU 功能，例如 USD/Alembic 导入导出或 OSL，并执行其相应 regression。

## 可控变量

- 模块和测试范围随实例冻结；编译并行数 BUILD_JOBS 与测试并行数 TEST_JOBS 独立记录。
- 冷/热依赖缓存、ccache/sccache、优化等级和 clean/incremental 是场景变量，不增加任务 ID。

## 预期资源形态

- compiler_cpu
- linker_memory
- process_fanout
- filesystem_metadata
- build_workspace
- large_cxx_link
- embedded_python
- cpu_render_validation

## 后端能力要求

- Linux x86_64、声明的 CPU 指令集与 ABI；可在任务私有前缀执行和加载本轮产物。
- 不要求 root、KVM、外网或物理 GPU；特殊测试能力在实例准入时显式检查。

## 离线依赖准备

- 固定 Blender source、官方依赖 bundle、Python、Cycles 依赖与测试数据版本/哈希。
- 所有 Git LFS/大型测试媒体和 render reference 在计时前物化；不把指针文件当测试数据。

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

- Blender

## 与已有任务的关系

与已有 CPU/GPU 渲染候选可能共享 Blender，但此任务主目标为从源码生成并验证完整工程发行包。

## 范围说明

- 规模等级为设计预估；当前未构建或实测耗时、内存、I/O 与进程数量。
- 无 GUI/headless 构建不代表通过 Eevee、物理 GPU、窗口系统或全平台 Blender CI。

## 官方来源

- [C_BLENDER_HEADLESS] [Blender headless CMake preset](https://github.com/blender/blender/blob/main/build_files/cmake/config/blender_headless.cmake) — 检查位置：WITH_HEADLESS and disabled audio/windowing preset
- [C_BLENDER_CONFIG] [Blender CMake options](https://github.com/blender/blender/blob/main/CMakeLists.txt) — 检查位置：WITH_GTESTS; WITH_CYCLES; device options; CYCLES_TEST_DEVICES
- [C_BLENDER_TESTS] [Blender Python and render test definitions](https://github.com/blender/blender/blob/main/tests/python/CMakeLists.txt) — 检查位置：bmesh_bevel, bmesh_boolean, mesh_join, mesh_validate, blendfile tests; cycles_<group>_<device>
- [C_BLENDER_GTEST] [Blender C/C++ tests](https://developer.blender.org/docs/handbook/testing/gtest/) — 检查位置：WITH_GTESTS and make test

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
