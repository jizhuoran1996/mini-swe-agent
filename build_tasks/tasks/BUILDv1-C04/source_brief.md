# BUILDv1-C04 · 构建流式图像处理 C/C++ SDK

Build a streaming image-processing C/C++ SDK

**主工程**：[libvips](https://github.com/libvips/libvips)  
**组别**：多媒体、图形与地理计算工程　**规划规模**：中型　**实施优先级**：pilot

**语言**：C；C++  
**构建系统**：Meson；Ninja  
**Canonical goal**：`engineering.build_install_test.libvips.linux_cpu`

## Agent 任务目标

交付可被 C/C++ 应用使用的 libvips 与命令行工具，支持给定图像格式和流水处理；通过线程、顺序访问及文件描述符相关回归。

## 官方工作流与派生方式

libvips 官方 Meson 编译、shell/C 测试及可选安装后 Python suite。

## 初始环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

## 需要完成的工作

- 构建共享 C/C++ API、工具和指定图像格式 loader/saver。
- 运行 Meson 注册的 CLI、格式、线程和状态测试，再安装并验证新 consumer。

## 目标范围

Linux CPU libvips/libvips-cpp 与 vips CLI；必需 PNG/JPEG/TIFF，其他格式为显式变体。

## 构建与测试入口

### Configure / Generate

```bash
meson setup "$BUILD_ROOT" "$SRC_ROOT" --prefix "$INSTALL_ROOT" --libdir lib --wrap-mode=nodownload -Dtests=true -Dtools=true -Dcplusplus=true -Dintrospection=disabled -Dmagick=disabled
```

- 追加 -Djpeg=enabled -Dpng=enabled -Dtiff=enabled，其他格式 feature 随实例冻结。

### Build

```bash
meson compile -C "$BUILD_ROOT" -j "$BUILD_JOBS"
```

### Package / Install

```bash
meson install -C "$BUILD_ROOT"
```

- 归档库、头文件、vips CLI、pkg-config 与必要格式模块。

### Official Tests

```bash
meson test -C "$BUILD_ROOT" --list
```

```bash
meson test -C "$BUILD_ROOT" cli formats seq stall threading keep token connections descriptors --print-errorlogs
```

- 扩展档按官方 CI 安装 pyvips 测试依赖后执行 python -m pytest -sv "$SRC_ROOT/test/test-suite"，确认链接本轮 libvips。

## 官方测试选择

- **selectors**：cli；formats；seq；stall；threading；keep；token；connections；descriptors
- **rationale**：除像素结果外覆盖顺序读、线程协作、连接和 FD 行为；未安装某格式不能令必需 formats 测试退化为空。

## 独立消费者验收

- 从安装前缀编译独立 C++ 管线，读入 TIFF、裁剪缩放并写出 PNG。
- 复核结果尺寸、元数据及像素容差；确认动态加载的 vips 与格式模块来自 INSTALL_ROOT。

## 交付物

- SDK 与 CLI 安装包
- Meson 测试日志及结果计数
- 格式 feature 清单
- 外部 consumer 源码及产物

## 后续使用

用同一安装包重新读取前轮输出并生成缩略图集合，检查模块可加载、FD 可释放及安装路径完整。

## 可选增量变化

- **enabled**：True
- **type**：optional_format_enablement
- **delta**：加入锁定的 OpenJPEG 或 HEIF 支持，使用同一构建树重新配置并编译。
- **acceptance**：新增实际编码/解码能力和对应本地测试，验证源码产物被更新。

## 同一任务的规模配置

### Core：最小完整交付

CPU 核心库、C++ API、PNG/JPEG/TIFF 和列出的官方 Meson 测试。

### Reference：正式参考配置

完整声明格式库和所有适配本地 Meson tests。

### Extended：扩展范围

更多真实格式 backend、模块及官方安装后 pyvips suite。

## 可控变量

- 模块和测试范围随实例冻结；编译并行数 BUILD_JOBS 与测试并行数 TEST_JOBS 独立记录。
- 冷/热依赖缓存、ccache/sccache、优化等级和 clean/incremental 是场景变量，不增加任务 ID。

## 预期资源形态

- compiler_cpu
- linker_memory
- process_fanout
- filesystem_metadata
- build_workspace

## 后端能力要求

- Linux x86_64、声明的 CPU 指令集与 ABI；可在任务私有前缀执行和加载本轮产物。
- 不要求 root、KVM、外网或物理 GPU；特殊测试能力在实例准入时显式检查。

## 离线依赖准备

- 预置 GLib、expat、libjpeg、libpng、libtiff、可选编码库及工具链。
- 扩展档 pytest/pyvips wheels 从离线缓存装入独立 venv；不使用已有 libvips wheel 混过构建。

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

- libvips

## 与已有任务的关系

与 CPU/Memory 图像处理任务可能共享 libvips 来源；这里交付源码构建后的开发库。

## 范围说明

- 规模等级为设计预估；当前未构建或实测耗时、内存、I/O 与进程数量。

## 官方来源

- [C_VIPS_BUILD] [libvips source installation](https://www.libvips.org/install.html) — 检查位置：Building libvips from source
- [C_VIPS_TESTS] [libvips Meson test definitions](https://github.com/libvips/libvips/blob/master/test/meson.build) — 检查位置：script_tests plus token, connections and descriptors tests
- [C_VIPS_OPTIONS] [libvips Meson options](https://github.com/libvips/libvips/blob/master/meson_options.txt) — 检查位置：tests/tools/cplusplus booleans; introspection and image-format features
- [C_VIPS_CI] [libvips official CI](https://github.com/libvips/libvips/blob/master/.github/workflows/ci.yml) — 检查位置：Configure/build/check/install and test/test-suite invocation

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
