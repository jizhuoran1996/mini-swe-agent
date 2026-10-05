# BUILDv1-B10 · 构建 OpenJDK 镜像并验收编译器与 JVM

Build an OpenJDK image and validate javac and the JVM

**主工程**：[OpenJDK](https://git.openjdk.org/jdk)  
**组别**：编译工具链与语言运行时　**规划规模**：大型　**实施优先级**：standard

**语言**：Java；C++；C；Shell  
**构建系统**：Autoconf；GNU Make；javac bootstrap；jtreg；gtest  
**Canonical goal**：`openjdk-image-source-build`

## Agent 任务目标

从源码生成可分发 JDK image，交付 javac、java、jar 和标准模块；在新应用目录编译、打包和执行 Java 程序，并验证本机 JNI 交互。

## 官方工作流与派生方式

OpenJDK configure, make images and named jtreg groups/directories

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置与目标 revision 兼容的 boot JDK、C/C++ 工具链、Autoconf、Make、jtreg 及所需图形/字体/音频开发库；参考测试无桌面会话要求。
- 若启用 gtest 或 tier1 profile，预载正确 Google Test 源码；不得在测试时现下测试框架。

## 需要完成的工作

- 配置 server HotSpot 和固定 release build，构建完整 images。
- 执行 jdk_lang、javac 和 native_sanity 的固定本机测试。
- 提取生成的 JDK image，在源树外编译和运行独立应用与 JNI 库。

## 目标范围

Linux x86_64 server JVM、javac、标准模块与完整 JDK image；不要求 GPU、显示服务器或系统级安装。

## 构建与测试入口

### Configure / Generate

- 在 SRC_ROOT 运行 bash configure --with-boot-jdk="$DEPS_ROOT/boot-jdk" --with-jtreg="$DEPS_ROOT/jtreg" --with-debug-level=release --with-jvm-variants=server --enable-jtreg-failure-handler=no

- 记录 configure 解析出的实际 CONF 和 build 输出目录；禁止用通配符选择旧配置。

### Build

- 在 SRC_ROOT 运行 make CONF="$JDK_CONF" JOBS="$BUILD_JOBS" images

### Package / Install

- 从本轮 build/<CONF>/images/jdk 复制完整 image 到 INSTALL_ROOT 并归档；java/javac/jar/jmods 与 native libraries 均保留。

### Official Tests

- 在 SRC_ROOT 运行 make CONF="$JDK_CONF" test TEST="jdk_lang test/langtools/tools/javac hotspot/jtreg/native_sanity" JTREG="JOBS=$TEST_JOBS"

## 官方测试选择

- **reference**：jdk_lang + test/langtools/tools/javac + hotspot/jtreg/native_sanity
- **rationale**：分别覆盖基础语言运行、Java 编译器及 JNI 本机接口；以 JTReg 解析出的确切描述符冻结集合。
- **counts**：保留 jtreg pass/fail/error/not-run 及已知排除清单；测试框架缺失不能被当成跳过整个任务。

## 独立消费者验收

- 仅用 INSTALL_ROOT/bin/javac/java/jar 编译、打包和运行含集合/线程/文件处理的应用。
- 由新 javac -h 生成 JNI 头，用预置 C 编译器构建小型 shared library，再由新 JVM 调用并验证数值结果。
- 检查 java.home、运行版本及模块路径；消费者运行时不依赖 boot JDK。

## 交付物

- openjdk-image.tar.gz
- configure/spec 与 boot-JDK 依赖清单
- JTReg 报告
- 应用 JAR、JNI 库与执行结果

## 后续使用

使用交付 JDK 对新增模块应用进行编译、打包和执行，证明镜像可在保留环境中持续用于开发。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 server JDK image
- **tests**：jdk_lang
- **deliverable**：可用 JDK 安装镜像

### Reference：正式参考配置

- **scope**：完整 JDK 与本机 JNI 验收
- **tests**：jdk_lang、javac 目录、native_sanity
- **deliverable**：编译器/JVM/JNI 开发环境

### Extended：扩展范围

- **scope**：相同 image，预置 jtreg/gtest 依赖
- **tests**：make test-tier1，固定平台条件及上游问题排除清单
- **deliverable**：同一 JDK 与更广官方 tier1 结果

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。
- 固定 JOBS、JTREG JOBS、JVM 内存选项和 native debug symbol 策略；编译与测试并发分别记录。

## 预期资源形态

- java_and_native_compilation
- boot_jdk_processes
- large_link_steps
- classfile_metadata
- jvm_test_processes
- image_packaging

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。
- 允许普通动态库加载、线程和子进程；JNI 消费者仅操作本 session 内的文件。

## 离线依赖准备

- boot JDK、jtreg、必要 gtest 与 Linux 开发库全部预置；不从互联网下载测试框架。
- --enable-jtreg-failure-handler=no 仅关闭失败后的 sudo 诊断钩子；测试本身仍完整保留失败。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 新 JDK image 内容完整，版本/配置与目标 source 对应。
- 冻结测试集合真实运行且结果满足验收。
- 消费者的 Java 编译、JAR 执行和 JNI 调用均来自新 JDK。

## 应拒绝的负例

- make 成功但复制到了另一 CONF 的历史 image。
- 用 boot JDK 编译/执行消费者造成假通过。
- 测试仅成功启动却未发现用例，或 JNI shared library 不能由新 JVM 加载。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- OpenJDK 单一上游；javac、HotSpot 和标准库是同一个交付工程的组成部分。
- 其他 JVM 任务使用的预置 JDK 是共享依赖，应在项目独立性统计中注明。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。

## 官方来源

- [B_JDK_BUILD] [Building the JDK](https://github.com/openjdk/jdk/blob/master/doc/building.md) — 检查位置：TL;DR; boot JDK; Run configure; Running make/tests
- [B_JDK_TEST] [Testing the JDK](https://github.com/openjdk/jdk/blob/master/doc/testing.md) — 检查位置：Configuration; TEST selection; JTReg; test tiers

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
