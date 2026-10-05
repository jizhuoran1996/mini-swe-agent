# BUILDv1-C01 · 构建可安装的 CPU 媒体工具链并通过 FATE

Build and validate an installable CPU media toolkit

**主工程**：[FFmpeg](https://github.com/FFmpeg/FFmpeg)  
**组别**：多媒体、图形与地理计算工程　**规划规模**：大型　**实施优先级**：pilot

**语言**：C；assembly  
**构建系统**：configure；GNU Make  
**Canonical goal**：`engineering.build_install_test.ffmpeg.linux_cpu`

## Agent 任务目标

为离线媒体处理环境交付从源码构建的 ffmpeg、ffprobe 和开发库；通过固定 FATE 测试，并证明独立程序能够链接新库读取和转码给定媒体。

## 官方工作流与派生方式

FFmpeg 官方 out-of-tree 构建、安装及 FATE 回归流程。

## 初始环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

## 需要完成的工作

- 检查目标 codec、demuxer、muxer 和 filter 清单后配置 CPU 工具链。
- 完整编译、安装到私有前缀，运行冻结 FATE 选择，打包二进制、库、头文件和 pkg-config 信息。

## 目标范围

Linux CPU ffmpeg/ffprobe；libavcodec、libavformat、libavutil、libavfilter、libswscale、libswresample；基线不包含 ffplay 和硬件设备测试。

## 构建与测试入口

### Configure / Generate

- 在空 BUILD_ROOT 中执行 "$SRC_ROOT/configure" --prefix="$INSTALL_ROOT" --enable-shared --disable-static --disable-autodetect --disable-ffplay --disable-doc --samples="$FATE_SAMPLES"。

- CPU 指令集基线、启用组件及声明外部 codec 随配置锁定；FATE_SAMPLES 是已预置数据。

### Build

```bash
make -C "$BUILD_ROOT" -j "$BUILD_JOBS"
```

### Package / Install

```bash
make -C "$BUILD_ROOT" install
```

- 归档 INSTALL_ROOT 并附配置摘要、组件清单、运行库解析结果。

### Official Tests

```bash
make -C "$BUILD_ROOT" fate-list
```

- make -C "$BUILD_ROOT" -j "$TEST_JOBS" fate SAMPLES="$FATE_SAMPLES"；核心档使用声明的 fate-* 子集。

## 官方测试选择

- **core**：fate-checkasm、fate-ffprobe_compact、fate-ffprobe_xml，加冻结的内建音视频 codec 选择。
- **reference**：对该构建实际启用组件运行完整 FATE；提前镜像并 hash 所需样本。
- **rationale**：覆盖组件识别、CPU 汇编和媒体结果；逐一记录不可用组件，不能现场改变样本或生成新的参考答案。

## 独立消费者验收

- 只从 INSTALL_ROOT 解析 FFmpeg 开发库，编译小型 libavformat consumer 并读取已知音视频样本。
- 用安装后的 ffmpeg 完成受控无损转码；独立核对流参数、帧/样本数和解码内容。

## 交付物

- 私有前缀安装归档
- FATE 测试选择、逐例结果和日志
- 源版本/配置/库清单
- consumer 源码、二进制及媒体结果

## 后续使用

接收另一种已声明媒体格式，使用同一安装产物完成探测与转码，证明安装包在第二轮仍可用。

## 可选增量变化

- **enabled**：True
- **type**：optional_feature_reconfiguration
- **delta**：在已有构建中加入已预置且锁定的 libvpx codec 支持，并交付相应编解码能力。
- **acceptance**：新增 codec 出现在实际能力清单，相关 FATE 与独立 consumer 通过。
- **note**：重新配置可能重建大量对象，按实际依赖行为计量，不预设增量一定便宜。

## 同一任务的规模配置

### Core：最小完整交付

标准内建 CPU 工具/库干净构建，运行冻结的核心 FATE 子集。

### Reference：正式参考配置

相同工程的完整 CPU 组件与全部适配 FATE 测试。

### Extended：扩展范围

增加明确的 libvpx/libx264 等源支持 codec 和对应本地测试；不是新的任务。

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

- 预置编译器、汇编器、GNU Make，以及已批准的 codec 依赖。
- FATE 样本同步在计时前完成；回放中不调用 fate-rsync 或对外提交测试报告。

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

- FFmpeg

## 与已有任务的关系

与已有 CPU 媒体处理任务共享 FFmpeg 来源；这里交付的是构建并验证的软件工具链，运行时媒体处理只是 consumer 验收。

## 范围说明

- 规模等级为设计预估；当前未构建或实测耗时、内存、I/O 与进程数量。

## 官方来源

- [C_FFMPEG_BUILD] [FFmpeg installation instructions](https://www.ffmpeg.org/doxygen/8.0/md_INSTALL.html) — 检查位置：INSTALL: out-of-tree configure, make, make install
- [C_FFMPEG_FATE] [FFmpeg Automated Testing Environment](https://www.ffmpeg.org/fate.html) — 检查位置：Using FATE; fate-list, fate, SAMPLES, subset selection
- [C_FFMPEG_OPTIONS] [FFmpeg configure options](https://github.com/FFmpeg/FFmpeg/blob/master/configure) — 检查位置：Configuration and program options; --disable-autodetect, shared/static, ffplay and docs

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
