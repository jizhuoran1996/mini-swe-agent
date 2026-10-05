# BUILDv1-C05 · 构建可复用的 CPU 视觉开发工具包

Build a reusable CPU computer-vision development kit

**主工程**：[OpenCV](https://github.com/opencv/opencv)  
**组别**：多媒体、图形与地理计算工程　**规划规模**：大型　**实施优先级**：standard

**语言**：C++；C  
**构建系统**：CMake；Ninja  
**Canonical goal**：`engineering.build_install_test.opencv.linux_cpu`

## Agent 任务目标

构建具有图像编解码、特征匹配、标定和视频处理能力的 CPU SDK；通过官方准确性回归并交付可独立编译的视觉应用。

## 官方工作流与派生方式

OpenCV 官方 BUILD_LIST 模块构建和 opencv_test_* accuracy suite。

## 初始环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

## 需要完成的工作

- 冻结目标模块及依赖，通过 CMake 构建共享 SDK 与真实测试二进制。
- 安装 CMake package、头文件和库，编译外部图像匹配 consumer。

## 目标范围

多个原生 CPU 视觉模块及开发 SDK；不把 CUDA/OpenCL/GPU runtime 正确性包含在此基线。

## 构建与测试入口

### Configure / Generate

```bash
cmake -S "$SRC_ROOT" -B "$BUILD_ROOT" -G Ninja -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DBUILD_LIST=core,imgproc,imgcodecs,features2d,calib3d,video,videoio,ml,photo,ts -DBUILD_TESTS=ON -DBUILD_PERF_TESTS=OFF -DWITH_CUDA=OFF -DWITH_OPENCL=OFF -DWITH_GTK=OFF -DWITH_QT=OFF -DOPENCV_DOWNLOAD_PATH="$DEPENDENCY_CACHE/opencv"
```

- 预置 opencv_extra/testdata；明确视频文件 backend，固定 CPU baseline/dispatch 与可选第三方组件。

### Build

```bash
cmake --build "$BUILD_ROOT" --parallel "$BUILD_JOBS"
```

### Package / Install

```bash
cmake --install "$BUILD_ROOT"
```

- 归档实际安装的 OpenCVConfig.cmake、模块库、开发头文件与 runtime 依赖清单。

### Official Tests

- 设置 OPENCV_TEST_DATA_PATH 指向已锁定 opencv_extra/testdata。

- 依次运行 BUILD_ROOT/bin/opencv_test_core、opencv_test_imgproc、opencv_test_imgcodecs、opencv_test_features2d、opencv_test_calib3d、opencv_test_ml；保存 gtest XML。

- 视频模块使用冻结的文件输入测试选择，不包含相机、外部流或硬件设备测试。

## 官方测试选择

- **mandatory_binaries**：opencv_test_core；opencv_test_imgproc；opencv_test_imgcodecs；opencv_test_features2d；opencv_test_calib3d；opencv_test_ml
- **rationale**：横跨内存/矩阵、图像变换、编解码、特征、标定及算法；每个二进制必须真正执行已冻结的适配测试。

## 独立消费者验收

- 外部 CMake 项目以显式 OpenCV_DIR 指向本轮安装；编译特征提取和配准应用。
- 在固定图像对上核对关键匹配、几何变换残差与写出图像；检查实际库路径，不接受系统 OpenCV。

## 交付物

- CPU SDK 安装归档
- CMake 配置与模块清单
- gtest XML 和计数
- consumer 应用、输入映射和输出

## 后续使用

收到另一组相机/图像输入，以已安装 SDK 编译扩展 consumer 并完成标定或配准，无需重新下载 OpenCV。

## 可选增量变化

- **enabled**：True
- **type**：optional_module_enablement
- **delta**：在已有构建中启用已冻结 opencv_contrib 的一个真实 CPU 模块，例如 bgsegm。
- **acceptance**：该模块进入安装清单、官方模块测试执行且外部 consumer 可以调用新增功能。

## 同一任务的规模配置

### Core：最小完整交付

core/imgproc/imgcodecs/ts 的完整源码构建及相应 accuracy tests。

### Reference：正式参考配置

上述多模块 CPU SDK 与固定官方准确性套件。

### Extended：扩展范围

增加 DNN CPU 或具体 contrib 模块，预置所需模型/样本并扩展官方 tests。

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

- opencv 与 opencv_extra/contrib 使用兼容且锁定的 revisions。
- 预置 CMake 可能获取的第三方归档到 OPENCV_DOWNLOAD_PATH；禁网配置后检查模块未因下载失败被悄悄关闭。
- 固定图像/视频库、BLAS/TBB 等声明依赖。

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

- OpenCV

## 与已有任务的关系

与 GPU 视觉应用组共享 OpenCV 依赖可能性；该任务验收源码 SDK，不运行大型视觉训练。

## 范围说明

- 规模等级为设计预估；当前未构建或实测耗时、内存、I/O 与进程数量。

## 官方来源

- [C_OPENCV_CONFIG] [OpenCV configuration reference](https://docs.opencv.org/4.13.0/db/d05/tutorial_config_reference.html) — 检查位置：Build tests and limited modules; downloaded dependencies; CPU/GPU backends
- [C_OPENCV_TESTS] [OpenCV quality-assurance guide](https://github.com/opencv/opencv/wiki/QA_in_OpenCV) — 检查位置：Accuracy tests in modules/<module>/test and OPENCV_TEST_DATA_PATH
- [C_OPENCV_INSTALL] [OpenCV Linux installation](https://docs.opencv.org/4.1.2/d7/d9f/tutorial_linux_install.html) — 检查位置：Build/install; opencv_test_core and test-data setup

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
