# BUILDv1-B09 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从锁定源码自举并安装本机 rustc、std 和 rustdoc，交付能独立编译普通 Rust 工程与文档的工具链，验证编译成功和应被拒绝的语言案例。

### 提供的环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 完整预载 Rust 源码、LLVM 子模块、Cargo vendor 数据和该 revision 要求的 stage0 compiler/std/Cargo。
- 预置 C++ 工具链、CMake、Ninja、Python；stage0 是允许依赖，但目标 stage1/stage2 和对象缓存初始不存在。

### 工程范围

Linux x86_64 rustc、标准库和 rustdoc；reference build.extended=false 不额外交付 Cargo；LLVM 为本轮源码编译的 X86 后端。

### 工作要求

- 以配置文件关闭目标 rustc/CI LLVM 下载，编译 LLVM 和本机 Rust 工具链。
- reference 使用 stage2；运行固定 UI 子目录和标准库测试后安装。
- 用交付 rustc/std 编译新程序，并验证错误程序被拒绝；生成可打开的文档。

### 交付

- rust-toolchain.tar.gz
- bootstrap.toml/stage0/LLVM/vendor 清单
- UI 与 std 测试报告
- 消费者与 rustdoc 输出

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

用交付工具链编译新增的本地 library crate 和调用程序，跨 crate 验证 ABI/泛型行为及运行结果。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
