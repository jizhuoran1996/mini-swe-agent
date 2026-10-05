# BUILDv1-A08 · Agent 提示模板

Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。

## 初始请求

构建支持 8/16/32 位字符和 JIT 的 PCRE2 安装包，交付命令行搜索与可嵌入 API，并验证 Unicode 捕获及错误输入。

### 提供的环境

- 固定版本的完整源代码与源内测试资源；源码可写副本位于 SRC_ROOT。
- 工具链、声明的依赖和测试工具已预装并冻结；目标工程的 build/install 目录为空，目标对象缓存为空。
- BUILD_ROOT、INSTALL_ROOT、ARTIFACT_ROOT 为本 session 可写目录；BUILD_JOBS 与 TEST_JOBS 来自实验配置。

### 工程范围

8/16/32 位实现、JIT、POSIX 兼容接口及 grep；同一源代码以真实支持宽度形成多个 native 目标。

### 工作要求

- 预置版本匹配的 JIT 子模块，编译三种代码单元宽度、POSIX 层、pcre2grep 和测试程序。
- 运行 RunTest/RunGrepTest 对应 CTest、JIT 和 POSIX 官方验证。
- 新应用分别链接各宽度接口，核对 Unicode 匹配及 JIT 功能确实存在。

### 交付

- 多宽度 PCRE2 开发包
- 四类官方套件及内部 case 统计
- Unicode/JIT consumer 和 grep 验收结果

请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。

## 可选后续请求

request: 使用已交付三种编码接口解析后续日志，并返回匹配结果与非法表达式诊断。；state: 仅复用安装包和编译好的 consumer；保留 JIT/编码功能声明。

如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。
