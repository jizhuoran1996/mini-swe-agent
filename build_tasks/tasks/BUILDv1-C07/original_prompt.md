# BUILDv1-C07 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码交付可以在无窗口环境运行的 Godot 编辑器和 Linux 发布模板，完成引擎回归，并把给定小项目导出为独立可执行应用。

### 提供的环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

### 工程范围

Linux CPU headless/editor 和发布模板；引擎测试的 mock rendering/audio server 不等于图形硬件通过。

### 工作要求

- 构建 tests=yes 的编辑器及 template_release；两者源码和依赖一致。
- 运行 headless doctest 与 GDScript suite，使用本轮模板导出并启动 consumer 项目。

### 交付

- editor 与 Linux template 安装包
- SCons 配置/模块/来源清单
- doctest XML 与 GDScript 结果
- 导出的 consumer 应用及项目输入

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

接收对 consumer 场景/脚本的真实修改，用原编辑器重新导入和导出，再执行新包验证变化。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
