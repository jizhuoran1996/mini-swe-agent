# BUILDv1-C09 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

为地理数据处理工具交付支持指定本地栅格与矢量格式的 GDAL SDK、CLI 和 Python bindings，并验证坐标、数据读写和安装后的开发接口。

### 提供的环境

- 已冻结的目标源码、声明的离线依赖和工具链；目标工程没有预编译产物、对象文件或对象缓存。
- SRC_ROOT、BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为实例内独立路径；默认完整干净构建。

### 工程范围

本地 GeoTIFF/COG/VRT、GeoJSON/Shapefile/SQLite/GeoPackage 和坐标变换；不要求外部数据库、云对象服务或 proprietary drivers。

### 工作要求

- 明确 GTiff/COG/VRT/MEM/GeoJSON/Shapefile 及 SQLite/GeoPackage 等目标驱动。
- 构建 libgdal、CLI、Python bindings 与 C++ tests，安装后完成外部数据 consumer。

### 交付

- GDAL SDK/CLI/Python 安装包
- 驱动/PROJ/依赖清单
- C++ 与 Python 测试报告
- 独立 consumer 和地理数据产物

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

从上轮产生的数据建立新 VRT 或 GeoPackage 并重新打开，验证工作空间和本轮格式驱动持续可用。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
