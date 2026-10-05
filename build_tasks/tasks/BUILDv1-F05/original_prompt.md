# BUILDv1-F05 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码交付 NumPy wheel，包含数组/ufunc 原生扩展、线性代数与随机模块，以及可供下游扩展使用的开发头文件。

### 提供的环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 预装固定 C/C++ 编译器、Python headers、Cython、Meson 和选定 OpenBLAS/LAPACK；NumPy wheel 和其目标缓存为空。

### 工程范围

完整 CPU NumPy wheel 及头文件、原生模块。reference 官方非 slow suite 已明确排除慢例，不以本轮失败情况动态删例。

### 工作要求

- 配置所需 BLAS/CPU dispatch 并编译完整 NumPy wheel。
- 从安装环境执行官方数值测试。
- 检验矩阵、FFT/随机对象和数组持久化；扩展 profile 可验证 C API/F2PY。

### 交付

- NumPy wheel、BLAS/CPU 配置和原生扩展清单。
- 官方测试报告与独立数值/持久化检查。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

下游使用交付头文件和数组 API 编译一个小 C 扩展，并处理新增数组输入；这部分单独记录为消费验证成本。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
