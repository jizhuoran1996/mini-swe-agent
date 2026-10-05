# BUILDv1-C08 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

为无物理 GPU 的 sandbox 构建可安装的 Mesa 软件图形库及 Vulkan ICD，交付能够执行离屏图形程序的 CPU 运行栈。

### 提供的环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

### 工程范围

Linux LLVMpipe OpenGL/EGL/GLES 与 Lavapipe Vulkan CPU 软件实现；不使用实体 GPU 或 DRM render node 作为验收前提。

### 工作要求

- 配置 llvmpipe 与 swrast Vulkan 驱动，编译图形栈和单元测试。
- 安装本轮 EGL/GLES/driver/ICD 产物，运行软件渲染器测试与独立离屏应用。

### 交付

- Mesa 软件图形安装包
- Meson 配置、ICD/库清单
- 官方测试记录
- EGL 和 Vulkan consumer 及 readback 结果

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

新进程使用同一安装包执行不同离屏 shader 和 readback，检验可复用加载状态与应用兼容性。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
