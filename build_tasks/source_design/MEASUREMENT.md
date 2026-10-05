# 工程任务的资源测量

任务分组与规模等级帮助选择工程；CPU-heavy、memory-heavy、process/metadata-heavy 等标签在固定参考环境上测量后确定。仅凭仓库大小、语言、项目名或 `-j` 不能决定实际资源需求。

## 阶段与生命周期

分别记录 sandbox 准备、任务 configure/generate、compile、link、package/install、正式测试、独立 grader、等待和释放。构建系统能够给出 action 或 trace 时保留其阶段证据；阶段重叠时报告真实区间，不能将各阶段 p95 相加作为总体 p95。

单独报告真实工具区间的并集 wall time 与完整 session wall time；后台编译、测试服务及它们的子进程按实际生命周期归属，不能在启动命令返回后停止计量。agent LLM 的记录等待可以重放，构建进程的等待与完成必须来自当前执行。

## 推荐的参考画像

| 维度 | 核心字段 | 对本组任务的用途 |
|---|---|---|
| CPU | host CPU core·s；平均/峰值并行度；user/system 时间；throttled time | 区分持续编译工作和配置/工具启动开销 |
| 内存 | 明确口径的峰值与 GiB·s；anon/file/shmem 分解；OOM/限制事件 | 观察并行编译和大型链接的瞬时需求及跨轮驻留 |
| 工作空间 | 新增/可变状态峰值；对象/生成源码/安装包占用；状态保留 GiB·s | 观察大 build tree、产物留存及恢复成本 |
| 存储访问 | 工具逻辑读写；task-attributed block reads/writes；fsync 等关键事件 | 分开文件访问、页缓存命中和真实块设备流量 |
| 文件与进程 | 文件/inode 数、进程创建次数、峰值同时存活进程、FD 峰值 | 观察大量编译单元、代码生成、测试进程和小文件操作 |
| OS 交互 | process/exec/wait、open/stat/readlink/getdents、mmap/fault、futex、socket 等操作族 | 解释运行时/内核边界与隔离后端上的不同执行路径 |
| 压力诊断 | CPU/memory/I/O PSI、major/minor faults、run queue、cgroup 限制事件 | 区分资源竞争和软件路径开销 |
| 工作完成 | 配置功能、实际编译动作、测试统计、交付物身份、有效完成 | 防止缩减目标、缓存命中和失败使结果看起来更快 |

逻辑 I/O、块 I/O 和空间占用是不同量；代码树大也不保证产生大量 block reads。syscall 总数不能单独说明 gVisor 等后端的覆盖程度，应结合操作族、频率及相应工具活跃时长。tracing/sampling 的开销由独立 profiling run 评估，默认性能运行保持一致的观测配置。

宿主 CPU/内存成本覆盖 runner、容器运行时或 VMM，并说明共享进程的归因方式；guest 用量作为解释数据，不能与宿主用量重复相加。Native 与 VM 中页缓存的记账也可能不同，报告应明确比较口径。

## 集群实验中的使用

以完整 session 为调配单位，按画像选择 CPU、内存、状态规模和 process/metadata 的组合，同时独立控制计划到达率。固定 manifest 下报告正确完成率、goodput、计划到达到完成的延迟、排队、CPU core·s/有效完成和内存 GiB·s/有效完成；失败和未完成工作已产生的资源开销保留在分子中。

编译 jobs 与 sandbox CPU 配额分别冻结。作业数、测试线程、LTO/linker 线程以及 ML runtime 的线程池都可能改变同一项目的资源形态，因此它们进入实例配置，不能由 backend adapter 悄悄改写。

## 画像与规模

先跑小型试点，再为 core/reference/extended 逐个画像。记录 source/config/test hashes、参考宿主、内核、runtime、工具链、缓存声明和配额。规模等级 small/medium/large/very_large 是当前工程规划字段；正式画像保存实际数值及测量范围，不把规划级别转换成未经测量的 GB 或分钟门槛。
