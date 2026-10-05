# BUILDv1-C03 · 交付可开发和可测试的图像处理安装包

Deliver a tested image-processing SDK and CLI package

**主工程**：[ImageMagick](https://github.com/ImageMagick/ImageMagick)  
**组别**：多媒体、图形与地理计算工程　**规划规模**：中型　**实施优先级**：pilot

**语言**：C；C++  
**构建系统**：Autoconf configure；GNU Make  
**Canonical goal**：`engineering.build_install_test.imagemagick.linux_cpu`

## Agent 任务目标

构建支持指定 PNG/JPEG/TIFF/PDF 格式的 ImageMagick 工具与 C/C++ 开发接口；交付可以处理输入图像和文档、被独立应用链接的安装包。

## 官方工作流与派生方式

ImageMagick Unix 源码配置、安装和 make check。

## 初始环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

## 需要完成的工作

- 核对图像 delegate、字体与量化深度配置，完整构建 magick、MagickCore/Wand 和 Magick++。
- 先安装到私有前缀，再执行官方 make check 并打包运行资源。

## 目标范围

Linux 无 X11 图像处理 CLI + MagickWand/Magick++ SDK；PDF/PS 测试通过已声明的 Ghostscript delegate 运行。

## 构建与测试入口

### Configure / Generate

- 在声明构建目录执行 "$SRC_ROOT/configure" --prefix="$INSTALL_ROOT" --enable-shared --disable-static --without-x --without-perl --with-quantum-depth=16。

- 锁定 HDRI、线程、PNG/JPEG/TIFF delegate、Ghostscript、Freetype 和字体；本地测试 policy 允许该固定可信样本套件所需操作。

### Build

```bash
make -C "$BUILD_ROOT" -j "$BUILD_JOBS"
```

### Package / Install

```bash
make -C "$BUILD_ROOT" install
```

- 收集库、头文件、CLI、coder modules、delegate/policy/字体路径配置与安装清单。

### Official Tests

- 安装后 make -C "$BUILD_ROOT" check。

- 通过安装后的 magick identify -list configure 与 -list format 核验实际能力。

## 官方测试选择

- **reference**：官方 make check 的本地 suite；提供官方说明要求的 Ghostscript、Freetype、字体和测试 policy。
- **rationale**：格式、delegate 和资源路径是安装正确性的重要组成，不能把这些测试整组跳过。

## 独立消费者验收

- 从安装前缀编译独立 MagickWand 或 Magick++ consumer，进行 TIFF→PNG 转换和尺寸/颜色操作。
- 独立检查格式、几何、alpha 与数值容差；启动位置离开源码/构建目录后仍可找到 coder 和字体。

## 交付物

- 含配置资源的安装归档
- make check 日志与计数
- 格式/delegate 清单
- C/C++ consumer 及验证图像

## 后续使用

收到一份新的多页 TIFF 或固定字体文档，使用已有安装包生成分页图像，检查包内资源可持续使用。

## 可选增量变化

- **enabled**：True
- **type**：optional_delegate_enablement
- **delta**：基于不含 WebP 的已构建实例，加入已锁定 libwebp delegate 并重新构建安装。
- **acceptance**：新增格式的读写能力、官方相应测试和独立 consumer 均通过。

## 同一任务的规模配置

### Core：最小完整交付

PNG/JPEG/TIFF 图像 CLI 与开发库，冻结适用的官方测试选择。

### Reference：正式参考配置

完整声明图像格式、Magick++ 和文档 delegate；执行安装后的 make check。

### Extended：扩展范围

加入额外真实格式 delegate 与对应测试；不以像素处理重复循环扩大构建。

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

- 固定官方源码归档或 revision、编译器、libtool、编码库、Ghostscript、Freetype 和测试字体。
- delegate 与字体都预置；安装路径属于任务私有前缀，无需 sudo/ldconfig。

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

- ImageMagick

## 与已有任务的关系

与已有图像处理资源任务可共享库；此处完成源码构建与 SDK/安装包验证。

## 范围说明

- 规模等级为设计预估；当前未构建或实测耗时、内存、I/O 与进程数量。

## 官方来源

- [C_IM_BUILD] [ImageMagick advanced Linux source installation](https://imagemagick.org/advanced-linux-installation/) — 检查位置：Configure options; build, install and make check; delegates
- [C_IM_INSTALL] [ImageMagick source installation](https://imagemagick.org/install-source/) — 检查位置：Unix source build and make check

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
