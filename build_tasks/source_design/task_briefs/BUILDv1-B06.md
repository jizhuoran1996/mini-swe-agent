# BUILDv1-B06 · 构建并安装 Ruby 解释器与标准扩展

Build and install the Ruby interpreter and standard extensions

**主工程**：[Ruby](https://github.com/ruby/ruby)  
**组别**：编译工具链与语言运行时　**规划规模**：中型　**实施优先级**：standard

**语言**：C；Ruby  
**构建系统**：Autoconf；GNU Make；Ruby test-unit；MSpec  
**Canonical goal**：`ruby-runtime-source-build`

## Agent 任务目标

交付可供脚本工程使用的 Ruby 安装树，包含声明的默认 gems 与原生扩展；通过官方语言测试和新应用验证字符串、对象、文件与线程行为。

## 官方工作流与派生方式

Ruby autogen/configure/make, bootstrap tests, test-all and ruby/spec

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- BUILD_ROOT 固定为 SRC_ROOT/build，以匹配官方 out-of-tree 测试路径。
- 预置 bootstrap Ruby、Autoconf、C 编译器、libyaml/zlib/OpenSSL 等所需库以及源码声明的 bundled gem 归档；JIT 选择在配置清单中显式固定。

## 需要完成的工作

- 生成 configure，执行完整解释器和扩展构建。
- 运行 bootstrap tests 和 test/ruby 全目录，安装产物并检查声明扩展均可加载。
- 在源树外运行独立脚本并验收安装树对后续应用可用。

## 目标范围

Linux x86_64 CRuby 主解释器与声明的默认/原生扩展；reference 不把可选 JIT 作为隐式要求。

## 构建与测试入口

### Configure / Generate

- 在 SRC_ROOT 运行 ./autogen.sh

- 在 BUILD_ROOT 执行 ../configure --prefix="$INSTALL_ROOT"

- 将匹配 revision 的 JIT 与扩展选项固定到配置文件；不依据是否偶然检测到 Rust 自动改变范围。

### Build

```bash
make -C "$BUILD_ROOT" -j"$BUILD_JOBS"
```

### Package / Install

```bash
make -C "$BUILD_ROOT" install
```

- 归档 Ruby、标准库、默认 gems 和原生扩展，记录 RbConfig 与 gem 来源。

### Official Tests

```bash
make -C "$BUILD_ROOT" test
```

```bash
make -C "$BUILD_ROOT" test-all TESTS="../test/ruby/"
```

## 官方测试选择

- **reference**：bootstrap test target + test-all TESTS=../test/ruby/
- **rationale**：覆盖解释器对象、字符串、内存管理与并发等语言行为；避免需要在线 gem registry 的 Bundler 全套测试。
- **counts**：保留 test-unit 的测试/断言/skip/failure 数，不能仅检查 make 退出状态。

## 独立消费者验收

- 使用 INSTALL_ROOT/bin/ruby 检查 RbConfig.ruby、load path 及原生扩展位置。
- 运行 JSON 文件处理、线程队列和压缩 round-trip 夹具；结果与固定预期一致。
- 禁用外部 gem 下载，在新的应用目录重复加载默认库与原生扩展。

## 交付物

- ruby-install.tar.gz
- RbConfig/扩展/default-gem 清单
- bootstrap 与 test-all 报告
- 应用消费者输出

## 后续使用

新增脚本复用安装好的解释器、JSON/压缩库及线程队列完成另一批数据转换，验证不需要原构建目录。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：完整 Ruby 解释器和选定默认扩展
- **tests**：make test 与 test/ruby/test_string.rb
- **deliverable**：可运行安装树

### Reference：正式参考配置

- **scope**：同一完整解释器及默认 gems
- **tests**：bootstrap 与整个 test/ruby
- **deliverable**：Ruby 工程运行环境

### Extended：扩展范围

- **scope**：增加声明的语言规范验收
- **tests**：make test-spec SPECOPTS=../spec/ruby/core/；条件允许再扩展至锁定的 test-all 全集合
- **deliverable**：同一安装树与更广语言规范报告

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。
- 固定 JIT 模式、扩展集和 test-unit worker；C/Rust 工具链的出现不能自动改变范围。

## 预期资源形态

- native_interpreter_build
- generated_sources
- extension_linking
- many_test_processes
- small_file_metadata
- gem_install_io

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。

## 离线依赖准备

- 预载源码声明的 bundled gems 及开发库，并锁定所需 host Ruby。
- make/install 中任何默认 gem 获取都改用经过校验的本地缓存；禁止临时联网修补依赖。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 新 Ruby 与扩展可独立于源树使用；官方 suite 和应用结果均正确。
- 安装包中默认 gem/扩展版本与清单一致，测试包含真实断言。

## 应拒绝的负例

- bundled gem 在构建时在线下载造成输入漂移。
- 使用 bootstrap Ruby 执行消费者而非新解释器。
- 声明支持的原生扩展缺失且被测试整体跳过。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- Ruby 上游主仓库及其镜像的 ruby/spec/default-gem 依赖；各 gem 不另外计任务。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。

## 官方来源

- [B_RUBY_BUILD] [Building Ruby](https://docs.ruby-lang.org/en/master/contributing/building_ruby_md.html) — 检查位置：Quick start; dependencies; out-of-tree build and installation
- [B_RUBY_TEST] [Testing Ruby](https://docs.ruby-lang.org/en/master/contributing/testing_ruby_md.html) — 检查位置：Test suites 1–3; TESTS and SPECOPTS

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
