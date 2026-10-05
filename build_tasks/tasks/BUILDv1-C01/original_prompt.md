# BUILDv1-C01 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

为离线媒体处理环境交付从源码构建的 ffmpeg、ffprobe 和开发库；通过固定 FATE 测试，并证明独立程序能够链接新库读取和转码给定媒体。

### 提供的环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

### 工程范围

Linux CPU ffmpeg/ffprobe；libavcodec、libavformat、libavutil、libavfilter、libswscale、libswresample；基线不包含 ffplay 和硬件设备测试。

### 工作要求

- 检查目标 codec、demuxer、muxer 和 filter 清单后配置 CPU 工具链。
- 完整编译、安装到私有前缀，运行冻结 FATE 选择，打包二进制、库、头文件和 pkg-config 信息。

### 交付

- 私有前缀安装归档
- FATE 测试选择、逐例结果和日志
- 源版本/配置/库清单
- consumer 源码、二进制及媒体结果

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

接收另一种已声明媒体格式，使用同一安装产物完成探测与转码，证明安装包在第二轮仍可用。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
