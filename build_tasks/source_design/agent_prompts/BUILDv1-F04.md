# BUILDv1-F04 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码构建包含原生树和数值扩展的 scikit-learn wheel，供下游应用完成邻域查询与可重载的分类流水线。

### 提供的环境

- 固定源码及必要 submodules、依赖锁和预装编译工具；目标项目没有 wheel、对象文件或命中目标的编译缓存。
- 独立 BUILD_ROOT、ARTIFACT_ROOT、INSTALL_ROOT 和测试输出目录；消费端虚拟环境不含目标项目。
- 固定 NumPy/SciPy ABI 依赖、Cython/Meson/Ninja、OpenMP 与测试依赖；这些依赖可预装，scikit-learn 本身必须未构建。

### 工程范围

Linux CPU scikit-learn wheel，包含 Cython/native extensions；不是仅 Python metadata wheel，也不是重建其已固定 NumPy/SciPy 依赖。

### 工作要求

- 编译整个所选 scikit-learn wheel，保留 Cython→C/C++→shared object 的日志。
- 验证官方邻域树测试，reference 扩展到完整 neighbors tests。
- 在新消费端进行邻域查询和 Pipeline fit/predict/序列化重载。

### 交付

- 本轮 scikit-learn wheel 和 native extension/依赖清单。
- 邻域测试报告、消费端查询/预测结果及可重载对象。

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

新应用加载已经交付的 Pipeline，对新增行完成预测；如另做增量构建，必须先固定真实源码补丁。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
