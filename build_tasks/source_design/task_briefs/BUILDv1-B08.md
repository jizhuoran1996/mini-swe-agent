# BUILDv1-B08 · 从源码构建 Go 工具链并交付本机开发环境

Build a Go toolchain from source for native development

**主工程**：[Go](https://go.googlesource.com/go)  
**组别**：编译工具链与语言运行时　**规划规模**：大型　**实施优先级**：standard

**语言**：Go；Assembly；C；Shell  
**构建系统**：cmd/dist；Go bootstrap；Go test  
**Canonical goal**：`go-toolchain-source-build`

## Agent 任务目标

从目标源码构建完整 Go 工具链及标准库支持，交付可移至应用目录使用的 GOROOT，并用新工具链编译和测试一个无外部依赖的本机模块。

## 官方工作流与派生方式

Go src/make.bash bootstrap, cmd/go package tests, src/run.bash

## 初始环境

- 锁定完整项目源码、子模块及测试数据；目标项目无已有可执行文件、对象文件或编译缓存。
- 编译器、生成器和第三方依赖预先准备并锁定；安装前缀仅指向本 session 工作空间。
- 预置满足目标 revision bootstrap 规则的旧 Go 工具链；与目标源码和结果目录分离。
- 锁定 C 编译器及 CGO_ENABLED；目标源码树的 bin/pkg/build cache 初始为空，SRC_ROOT 是待构建 GOROOT。

## 需要完成的工作

- 通过 src/make.bash 真正自举目标编译器和工具。
- 用目标 bin/go 执行固定官方标准包测试，并关闭成功结果缓存。
- 交付完整 Go 树，在新消费者目录编译、测试和运行模块。

## 目标范围

linux/amd64 Go compiler、linker、标准库与本机 cgo 支持；没有在线 module 解析。

## 构建与测试入口

### Configure / Generate

- 设置本实例 GOROOT_BOOTSTRAP 为 DEPS_ROOT 中固定 bootstrap 工具链；GOTOOLCHAIN=local，GOPROXY=off。

- 将目标构建 GOCACHE 指向本实例初始为空的目录；CGO_ENABLED=1 的 reference 预置 C 工具链。

### Build

- 在 "$SRC_ROOT/src" 运行 ./make.bash

### Package / Install

- 将 make.bash 生成的完整 Go 工具链树部署到 INSTALL_ROOT 并归档；保留所需 bin/pkg/src/lib 与版本/许可文件，排除版本控制元数据。

- 记录新 bin/go 的 GOROOT 和工具路径；消费者从安装树运行。

### Official Tests

```bash
"$SRC_ROOT/bin/go" test -count=1 -json bytes strings encoding/json compress/gzip sync runtime
```

- 测试工作线程及 build -p 上限由实例配置固定。

## 官方测试选择

- **reference**：bytes、strings、encoding/json、compress/gzip、sync、runtime
- **rationale**：覆盖数据处理、同步和运行时；不把下载第三方模块的 cmd/go 端到端集合作为默认依赖。
- **counts**：采集 go test JSON 中的包/测试 action；拒绝缓存结果、零测试包和测试异常结束。

## 独立消费者验收

- INSTALL_ROOT/bin/go 的 GOROOT/GOTOOLDIR 指向交付树；输出与锁定目标源码匹配。
- 源树外模块包含编码、压缩、goroutine/channel 与一个本地 cgo 函数；用新 Go build/test 后运行。
- 以 GOTOOLCHAIN=local、GOPROXY=off 执行，确保没有自动选择下载的另一个编译器。

## 交付物

- go-toolchain.tar.gz
- bootstrap/目标工具链身份报告
- 标准包测试 JSON
- 消费者源码/二进制与结果

## 后续使用

为新提供的纯本地 module 使用已安装工具链编译和运行单元测试，展示交付产物能继续支持真实工程。

## 可选增量变化

- **enabled_by_default**：False
- **kind**：frozen_legitimate_source_patch
- **patch_binding**：builder_required_only_if_variant_enabled
- **protocol**：保留已完成构建树；选择上游已有、语义明确且有回归测试的真实修改，锁定 base/patch hashes 后重建。没有绑定补丁时仅运行完整构建基线。
- **acceptance**：修改对应的回归测试与消费者验收通过；记录实际重新编译范围；touch-only 或 no-op rebuild 仅可作为诊断。

## 同一任务的规模配置

### Core：最小完整交付

- **scope**：linux/amd64，CGO_ENABLED=0
- **tests**：bytes/strings/encoding/json/compress/gzip
- **deliverable**：完整纯 Go 本机工具链

### Reference：正式参考配置

- **scope**：linux/amd64 + cgo
- **tests**：六个固定包和 cgo 消费者
- **deliverable**：可构建含本地 C 依赖的工具链

### Extended：扩展范围

- **scope**：保持目标不变，增加完整官方本机 bootstrap 测试
- **tests**：在 src 运行 ./run.bash；精确固定测试能力与 timeout
- **deliverable**：同一 Go 工具链及更广运行时/工具测试报告

## 可控变量

- 冻结构建并行度与测试并行度；它们是场景参数，不生成新的 task ID。
- 统一限制 session 的 CPU、内存、进程数和工作盘；实际峰值与总量由参考运行测量。
- GOMAXPROCS、go build 的包并发和测试进程并发分别固定；初始 GOCACHE 与 module cache 分开。

## 预期资源形态

- compiler_bootstrap
- parallel_package_build
- link_steps
- many_processes
- small_files
- runtime_tests

## 后端能力要求

- Linux x86_64；可在工作空间执行新编译的程序、创建子进程及普通用户文件；无默认 root、GPU 或外部集群要求。

## 离线依赖准备

- bootstrap Go、系统 C 工具链及所有官方测试数据预装；目标模块不使用外部 module。
- GOTOOLCHAIN=local 禁止自动 toolchain 下载；标准包测试固定本地范围。

## 回放与状态

- 保持 configure→真实构建完成→测试/安装→消费者验收依赖；以子进程退出及完整日志判定完成。
- 冻结源码与配置，保留构建树用于可选后续工作；PID、临时目录与本地端口绑定本轮实际值。
- 时间戳、构建 ID 和归档顺序可随构建变化；使用功能和来源验证，除专门可复现构建场景外不要求逐字节相同。

## 最终 oracle

- 产物来自目标源码而非 bootstrap 安装；新编译器/stdlib/tool 路径闭合。
- 真实重跑的官方测试和消费者断言都通过。

## 应拒绝的负例

- 仅把 bootstrap Go 复制为交付物。
- go test 输出 cached 或未执行用例。
- 消费者自动下载更高版本工具链或链接缺失 cgo 依赖。

## Builder 实施工作

- 将来源分支解析为不可变 revision，冻结工具链、依赖、配置及所有测试清单。
- 实现安装包清单、来源路径验证和独立消费者夹具；基于参考运行确定非空测试数及允许跳过项。
- 运行参考构建后记录实际时间、CPU、内存、磁盘、进程和文件行为；据此设置资源准入，不能以计划规模代替测量。

## 源码血缘

- Go 单一工程，自举依赖是声明工具链，不额外算任务。

## 与已有任务的关系

与先前 CPU/内存任务中可能运行的同名工具保持来源关联；这里的目标是从源码构建并验收工程产物，原有运行负载不计为本任务的独立软件来源。

## 范围说明

- 规模分级为设计预估；尚未执行构建或测量资源。
- 测试通过只覆盖声明的 Linux 主机功能和固定测试集合，不代表上游全部平台 CI。
- 完整 run.bash 范围随 revision 改变；扩展 profile 必须先解析工具和系统能力，不能把所有 skip 当成功。

## 官方来源

- [B_GO_BUILD] [Installing Go from source](https://go.dev/doc/install/source) — 检查位置：Bootstrap toolchain; Install Go; Testing; environment variables
- [B_GO_TEST] [Go command: Test packages](https://pkg.go.dev/cmd/go) — 检查位置：Test packages; Testing flags
- [B_GO_RUN] [Go src/run.bash](https://go.dev/src/run.bash) — 检查位置：run.bash body

任务阶段：`source_grounded_design`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。
