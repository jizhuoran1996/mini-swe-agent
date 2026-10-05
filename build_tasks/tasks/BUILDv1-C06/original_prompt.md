# BUILDv1-C06 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

为渲染 worker 从源码构建 Blender，交付包含 Python 运行时和所需资源的 headless 发行目录；验证几何编辑、blend 文件读写及 CPU Cycles 渲染。

### 提供的环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。
- 与源码匹配的 Blender tests/files 数据树已完整物化；所需 OpenImageIO oiiotool 与 CPU Cycles 依赖可用。

### 工程范围

完整 Linux headless Blender，几何/文件 API 和 CPU Cycles；headless preset 关闭音频/视频等特定功能，目标清单照实际 preset 冻结。

### 工作要求

- 使用官方 headless preset 配置完整 Blender，启用测试和 CPU Cycles。
- 编译链接大型应用及测试、完成安装，执行明确的无 GUI regression，并从安装目录运行外部脚本。

### 交付

- 可执行 headless 发行目录归档
- 源/依赖/preset 和 CPU device 清单
- CTest 和 render-test 报告
- 外部场景脚本、blend 与验证帧

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

用已安装应用加载上一轮 blend，修改材质或几何再输出第二个场景与渲染，检验持续 workspace 与产物兼容性。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
