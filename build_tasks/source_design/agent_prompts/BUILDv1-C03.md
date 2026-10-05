# BUILDv1-C03 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

构建支持指定 PNG/JPEG/TIFF/PDF 格式的 ImageMagick 工具与 C/C++ 开发接口；交付可以处理输入图像和文档、被独立应用链接的安装包。

### 提供的环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

### 工程范围

Linux 无 X11 图像处理 CLI + MagickWand/Magick++ SDK；PDF/PS 测试通过已声明的 Ghostscript delegate 运行。

### 工作要求

- 核对图像 delegate、字体与量化深度配置，完整构建 magick、MagickCore/Wand 和 Magick++。
- 先安装到私有前缀，再执行官方 make check 并打包运行资源。

### 交付

- 含配置资源的安装归档
- make check 日志与计数
- 格式/delegate 清单
- C/C++ consumer 及验证图像

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

收到一份新的多页 TIFF 或固定字体文档，使用已有安装包生成分页图像，检查包内资源可持续使用。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
