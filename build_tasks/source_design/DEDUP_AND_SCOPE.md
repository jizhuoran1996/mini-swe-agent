# 任务计数、血缘与覆盖边界

60 个 canonical task 对应 60 个主工程的构建交付。profile、parallelism、compiler、cache、clean/incremental 场景是实例配置，不能作为新增任务数量。TypeScript、Rollup、Babel、esbuild、SWC 都有各自源码与构建交付目标；同为 JavaScript 工具链不意味着它们只是相同工程的开关变化。

大型框架和工具链可能共享 LLVM、XLA、BLAS、OpenSSL、压缩库及其他依赖。`upstream_repo`、`canonical_goal_key` 和 `source_lineage` 支持按主工程和依赖家族两种粒度分析。统计软件多样性时不能把每个重复出现的依赖当成独立实现。

前面的 CPU、Memory、I/O、Network、GPU 包可能把 PyTorch、数据库或编解码器当作运行时计算工具。本包的交付目标是从源码生成它们、测试并发布到任务范围内供消费者使用，因此是不同工作负载；但它们的上游软件血缘仍相关。

## 本包补充的工程行为

- 中小型 native libraries：配置探测、短编译动作、共享/静态产物和大量小测试。
- 编译器与语言 runtime：bootstrap、生成代码、大链接、复杂测试 harness。
- 多媒体与图形工程：模块/插件编译、原生库组合、资产和无头测试。
- 数据库与服务软件：原生工程加本地服务测试、文件/进程与临时状态。
- JVM/JS 工程：依赖图、代码生成、打包和大量 runtime 测试。
- ML/数值框架：C/C++/Fortran/Cython/Rust/XLA 等混合构建、wheel 交付与 native API 验收。

这些预期形态帮助挑选任务，不自动证明 CPU、内存或 syscall 已达到高需求区间。后续按实际画像重分类，并查看各资源区间的独立工程数量。

## 继续扩展的方向

本版围绕用户要求的工程规模与构建测试，不覆盖 Windows/macOS 工具链、内核/驱动开发、交叉设备调试、分布式编译、生产服务发布或多租户 GPU runtime 管理。这些可以是后续独立工作流。尤其“部署服务—修改—从 sandbox 外部验收”需要入口访问、长驻服务生命周期和请求行为，不应仅用本包的数据库 smoke consumer 代替。
