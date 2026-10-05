# 测试与独立验收

一个任务的成功同时要求：声明的工程确实从源码构建；指定的官方测试非空且得到允许的结果；交付物能够被独立使用。`--version`、编译命令退出码或 agent 编写的成功说明不能单独完成验收。

## 1. 冻结测试集合

任务卡中的官方 target、文件路径或 suite 是选择入口。builder 在固定版本上展开这个入口，保存测试集合或目标集合、过滤规则、固定排除项及原因、fixture 和必要数据；之后所有后端使用同一规格。不能把某个后端运行失败的测试临时删除。

记录 discovered、selected、executed、passed、failed、skipped、expected-failure 和 timeout。各测试框架层级不同，suite、test binary 与 test case 的数量不要混用；schema 同时保存 `count_unit` 和原始报告。无法提前完全发现动态测试时，冻结发现程序与输入，在运行中验证非空及约定的关键 case。

CTest 可以先用 `--show-only=json-v1` 取得测试描述，再执行绑定后的选择；支持的版本使用 `--no-tests=error` 拒绝空测试。JUnit 输出不等于独立证明，应与实际启动记录、日志和结果交叉核对。参见 [CTest official manual](https://cmake.org/cmake/help/latest/manual/ctest.1.html)。

## 2. 三层验收

| 层次 | 检查内容 | 示例 |
|---|---|---|
| 构建来源 | 源码/config/toolchain 的内容引用；实际编译/链接日志；产物路径、格式和启用功能 | PyTorch wheel 含本次构建的 native extensions，Clang 来自新安装前缀 |
| 工程测试 | 冻结的官方测试集合确实运行；测试统计、退出码和错误分类 | CTest、pytest、lit、jtreg、Maven/Gradle、项目自带 harness 的指定集合 |
| 独立消费 | 在源码树之外的新目录或环境，用交付物完成小而真实的功能目标 | 编译并运行 C consumer；安装 wheel 执行张量运算；运行新构建数据库并校验 SQL 结果 |

消费者用量保持小，目的是证明产物可用而非混入另一类大型性能负载。用户明确要求的工程测试属于任务工具执行；grader 额外执行的复核单独记账。服务型消费者只创建本地、任务范围内的服务及数据目录，结束时释放；完整外部服务部署属于后续独立任务组。

## 3. 产物来源必须可检验

Python consumer 在源码树外的独立环境中安装本次 wheel，记录模块、native extension 及实际加载库路径；避免 `PYTHONPATH` 或系统 site-packages 指向别处。C/C++ consumer 检查编译链接选项和实际加载的库。CLI/编译器用明确的产物路径，检查二进制身份及生成结果。JAR/npm/静态资源包同样需要确认消费的是本次构建的包。

artifact hash 用于标识交付物，通常不要求不同后端构建的二进制逐字节相等。时间戳、路径、build ID、压缩格式元数据可能不同；字节可复现性需要单独配置，例如固定时间源和 reproducible-build 设置。功能输出则采用任务卡给定的精确值、结构性条件或数值容差。

## 4. 负例和结果状态

必须拒绝：只安装发布版、配置自动关闭要求的组件、零测试、错误测试范围、日志伪造、source-tree fallback、只运行版本号、缺少必需产物、后台进程未完成就提交。显式标记不支持的能力与预先批准的 test skip，并与实际测试失败区分。

结果保留应用测试失败、构建失败、依赖缺失、OOM、timeout、sandbox/通信故障及截止时未完成。编译器的负测试可能预期输入编译失败，这类预期行为由 upstream harness 判定，不能把所有非零子进程都视作基础设施故障。

`templates/test_evidence.template.json` 和 `templates/run_result.template.json` 给出统一报告字段。任务专用验证器负责把框架自己的语义映射到它们。
