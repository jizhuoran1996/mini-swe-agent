# BUILDv1-C10 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

交付可被第三方 C++ 工程使用的科学数据、几何和可视化 SDK，支持读写 XML 数据与 CPU 离屏绘图；验证安装后模块依赖和渲染路径。

### 提供的环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

### 工程范围

Linux CPU 数据/几何/I/O SDK 与 reference 的 Mesa EGL 离屏渲染；明确无 MPI、Qt、物理 GPU 条件。

### 工作要求

- 构建明确的 Common/Filters/IO 模块及 reference 中的 RenderingOpenGL2。
- 安装完整 SDK，运行数据/过滤器/文件格式回归和真实 CPU EGL rendering tests。

### 交付

- 科学 SDK 安装包
- 模块/依赖/Mesa/EGL 配置清单
- CTest 与图像比较结果
- 独立 consumer、网格和截图产物

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

为 consumer 加入另一种过滤器并重新编译运行，复用原 SDK 与上轮 XML 产物，验证安装包开发接口完整。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
