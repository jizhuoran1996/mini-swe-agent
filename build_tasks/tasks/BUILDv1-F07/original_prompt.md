# BUILDv1-F07 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码编译 pandas 的底层扩展并交付 wheel，让独立应用可靠地处理带时间戳和缺失值的分组分析及索引操作。

### 提供的环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 提供固定 NumPy、Cython/Meson/Ninja、Python、时区库和 pytest 依赖；pandas 未预装，源码版本 tags/metadata 已冻结。

### 工程范围

pandas wheel 的 Cython/native libs、时序和数据框接口；没有远程 SQL 服务或公开对象存储依赖。

### 工作要求

- 通过 mesonpy 编译 native extensions，生成可独立安装的 wheel。
- 运行 libs/groupby/tslibs 对应官方 tests，报告明确的 skip。
- 使用新安装完成固定小表的分组、时间索引和文件重载核验。

### 交付

- pandas wheel、依赖/ABI/构建记录。
- 官方 libs/tslibs/groupby 测试报告和消费端数据工件。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

另一应用对追加的时间段使用同一安装和保存的数据重新聚合，检验交付后状态与类型语义。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
