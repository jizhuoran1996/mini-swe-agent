# 来源、版本和依赖锁定

## 来源到任务

每个任务绑定一个主工程、官方构建或测试工作流、具体构建产物，以及一个独立消费者目标。`sources.json` 记录检查过的页面/源码文件和支持的内容；`source_ids` 将任务和证据相连。目录中的分组是工程类别，资源分类来自后续固定参考配置上的测量。

源码浏览时的分支或 release tag 不自动等于完整可复现实例。实例构建时解析并保存 commit/tree/archive hash、子模块 revision、构建文件版本、测试数据清单和工具链信息。若任务卡指定版本，例如经典 TypeScript 或固定 Redis release，必须使用对应版本的构建方式，不混用 main 文档。

## 默认离线构建环境

预先准备依赖后关闭公网依赖，不让 package manager 静默下载目标工程的发布版产物来替代构建。构建所需的编译器、bootstrap runtime、BLAS、Java、Python 等是声明的输入；目标工程生成的编译器、runtime、共享库或 wheel 则是输出，两者必须分别记录。

| 生态 | 需要预置/锁定的内容 | 常见误判 |
|---|---|---|
| C/C++/Fortran | 编译器、链接器、sysroot、系统库、生成器、CMake/Meson/Autotools、外部源码 | configure 自动关闭缺失功能，得到缩水构建 |
| Python/native | Python 版本、PEP 517 backend、构建依赖 wheel、Cython/Pythran/Meson、BLAS 等 | 安装发布版 wheel；从源码目录误导入 |
| Rust | rustc/cargo、crate lock 和 vendor/cache、目标工具链 | 使用远端编译输出或系统同名 binary |
| Go | bootstrap Go、模块锁/缓存、CGO 工具链 | 成功测试缓存让测试没有再次运行 |
| JVM | JDK/bootstrap JDK、Gradle/Maven、插件与依赖缓存、测试工具 | 离线缓存漏插件，或只运行空模块任务 |
| JavaScript/TypeScript | Node、package manager、lockfile、registry cache、原生模块构建依赖 | 打包现成 JS 或下载原生 binary，未编译要求的工程 |
| Bazel | Bazel/Bazelisk、模块/WORKSPACE 依赖、repository cache、工具链与外部 archive | 把 repository cache 误当 action cache；远端执行替代本地受测 CPU |

任务卡给出具体项目的入口与依赖要求。离线环境需要一次完整预演确认：项目常在 configure、测试发现或测试运行阶段额外获取资产，不能只以 package manager install 成功作为依赖准备完成。

## 输出与输入的边界

源码及只读依赖可用共享只读存储，构建树、安装前缀、临时文件和本地服务数据目录属于本 session。预先准备的工具链不算目标工程构建产物；若要研究从零构建依赖闭包，应另设 profile，并将这个范围对所有后端保持一致。

自举工具可以与目标工程同名，例如构建编译器时使用旧编译器、TypeScript 的 LKG 或 Rollup 的开发依赖。它们以 bootstrap-only 身份进入锁定的依赖环境，并记录使用阶段；新产物和独立 consumer 使用不同路径。禁止预装产物替代本次构建，不等于禁止合法的自举工具链。

大型工程重用 LLVM、XLA、OpenSSL、BLAS 等依赖并不产生新的独立软件家族。`source_lineage` 应说明哪些依赖被预装、哪些实际进入计时编译。扩展 CUDA 编译时锁定 SDK、架构列表及版本；编译成功与真实设备测试是两个结果。

## 发布和重建

建议公开任务提示、配置、源码引用、依赖锁文件、补丁和验证器。第三方源代码/测试数据是否能再分发按各自许可处理；本包只包含任务设计和来源定位，不打包第三方工程。已安装的系统包也应保存版本清单与基础镜像内容引用。

`templates/source_dependency_lock.template.json` 是实例锁定字段的起点。许可、访问方式、内容 hash 和实际构建能力都在实例化阶段完成，不以网页标题或当前分支名称代替。
