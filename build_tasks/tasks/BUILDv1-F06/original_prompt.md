# BUILDv1-F06 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码交付具有数值原生扩展的 SciPy wheel，使下游环境能够求解线性系统和约束优化问题，并通过对应官方模块测试。

### 提供的环境

- 冻结源码及必要 submodules、预装工具和依赖；无目标项目的已建二进制、对象缓存或 wheel。
- 分离 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；新的消费环境没有目标包。
- 提供固定 C/C++/Fortran 编译器、BLAS/LAPACK、NumPy ABI、Cython/Pythran/pybind11、Meson 及测试依赖。

### 工程范围

完整 Linux CPU SciPy wheel；reference 验证 linalg/optimize，扩展范围增加真实官方模块而非反复求解同一小问题。

### 工作要求

- 编译声明范围的完整 wheel，记录 Fortran/Cython/Pythran 生成和链接步骤。
- 在本轮 wheel 环境运行 linalg 和 optimize 的官方 CPU tests。
- 新消费端对已知解问题计算残差/目标函数并核查动态依赖。

### 交付

- SciPy wheel、编译器/BLAS/ABI 清单。
- 官方模块测试报告、独立数值验收与动态库来源报告。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

下游应用加载该 wheel 求解新的边界条件或右端项，并保存结构化计算结果；延续原安装与 workspace。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
