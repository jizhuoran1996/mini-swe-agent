# BUILDv1-B10 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

从源码生成可分发 JDK image，交付 javac、java、jar 和标准模块；在新应用目录编译、打包和执行 Java 程序，并验证本机 JNI 交互。

### 提供的环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置与目标 revision 兼容的 boot JDK、C/C++ 工具链、Autoconf、Make、jtreg 及所需图形/字体/音频开发库；参考测试无桌面会话要求。
- 若启用 gtest 或 tier1 profile，预载正确 Google Test 源码；不得在测试时现下测试框架。

### 工程范围

Linux x86_64 server JVM、javac、标准模块与完整 JDK image；不要求 GPU、显示服务器或系统级安装。

### 工作要求

- 配置 server HotSpot 和固定 release build，构建完整 images。
- 执行 jdk_lang、javac 和 native_sanity 的固定本机测试。
- 提取生成的 JDK image，在源树外编译和运行独立应用与 JNI 库。

### 交付

- openjdk-image.tar.gz
- configure/spec 与 boot-JDK 依赖清单
- JTReg 报告
- 应用 JAR、JNI 库与执行结果

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

使用交付 JDK 对新增模块应用进行编译、打包和执行，证明镜像可在保留环境中持续用于开发。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
