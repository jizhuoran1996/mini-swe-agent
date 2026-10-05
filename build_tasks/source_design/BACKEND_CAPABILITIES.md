# 后端能力与任务边界

六组的默认目标是 Linux x86_64 CPU 源码构建。所需 CPU ISA、工具链、文件系统和内核能力仍按 task instance 声明，不假设所有隔离后端支持相同测试。

| 能力 | 本包中的用法 | 比较方式 |
|---|---|---|
| 多进程/线程、信号、等待、mmap | 编译器、链接器、代码生成和测试 harness 的基本工作 | 默认路径，记录实际失败与运行成本 |
| 可写空间、symlink、执行权限、文件锁 | build tree、临时文件、安装前缀及测试数据库 | 初始空间和语义要求提前声明 |
| Loopback TCP/Unix sockets | curl/事件库测试、数据库和服务型产物的本地验收 | 允许任务范围内服务；不需要公网 |
| shared memory、特定 syscall | 部分数据库、runtime、系统测试 | 预先定义 capability profile 和支持集合 |
| 软件图形/无头运行 | Mesa 软件渲染、Blender CPU/headless、Godot/VTK 选定测试 | 绑定具体 software/offscreen 配置和本地资产 |
| GPU SDK | ML/图形工程可选设备代码编译 | 与真实 GPU runtime 测试分别记录 |
| GPU device | 可选扩展测试 | 单独能力子集，不以 CPU 构建成功代表设备通过 |
| 特权操作、嵌套虚拟化、外部云集群 | 默认不依赖 | 如后续加入，单独规格与对照集合 |

目标工程依赖的 `ptrace`、namespace、seccomp、特殊文件系统或用户身份行为必须检查具体测试。缺少能力是支持性结果；不能通过 blanket skip 混入同一成功分母。测试选择在参考实例阶段冻结，backend adapter 不负责修改工程目标。

这里的数据库和服务器任务验收“本次构建的程序能否被消费”，不要求开放公网 endpoint、发布生产服务或操作用户现有环境。“sandbox 内服务部署、修改与外部验收”可以单独构造后续任务包，覆盖长驻服务、入口路由和跨轮配置管理。
