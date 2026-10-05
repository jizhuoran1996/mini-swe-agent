# GPU 资源准入与测量

本文件规定如何把来源派生任务变成可比较的 GPU 轨迹。功能正确、GPU 执行成立和资源类别是三个独立结果。本包没有提供实机性能数字。

## 1. 正式工作负载的准入

1. 固定源码、模型、tokenizer/processor、输入清单、参考配置和评价器；模型与数据分别记录版本和哈希。
2. 用 debug 输入验证读取、真实 GPU 执行、交付与负例检查。debug 不进入正式高资源语料。
3. 运行 task card 的 reference_large 配方。确实执行当前这次训练、推理、仿真或数据计算；缓存旧答案不构成 GPU 轨迹。上游已有 checkpoint 可以是声明的初态，但不能作为本次训练产物直接交差。
4. 从任务环境内记录实际设备标识、执行进程、CUDA/其他 GPU runtime 版本和完成事件；结合宿主设备计量确认工作发生在分配的 GPU 上。设备可见、nvidia-smi 成功、分配了一个 tensor 均不能单独证明有效 GPU 执行。
5. 独立检查真实产物或后续服务结果。对生成式/近似/数值任务，内容完整性和任务质量分别检查；质量界限来自锁定参考流程或明确继承的源协议，不能仅信任务自报指标。
6. 采集完整 session 的资源时间序列，包含初始化、工具执行、模型等待、后台工作、应用 checkpoint、结束和清理。
7. 按观察标记 compute_activity、device_resident_state、device_memory_pressure、transfer_activity、collective_communication、host_io_mixed、lightweight 等形态。标签可重叠。合法优化让任务变轻时保留功能结果并重新画像。
8. 多次参考执行后冻结 profile 和采用的功能/质量规则；不同后端重放同一 manifest。用于优化算法的自由度在 live-agent 采集阶段，基础设施对比固定实际操作及配置。

## 2. 不用单个 GPU utilization 定义“大”

一个长数据处理作业可以持续使用 GPU，但显存并不大；一个大模型服务可以在两次请求间保留大量显存但几乎不计算；一项多卡任务可能受通信限制。下面的量应配合观察。

| 范围 | 主要量 | 解释要求 |
|---|---|---|
| 完成行为 | 有效完成、失败、未完成、planned-arrival 到完成的时间 | 保留 OOM、超时、设备/API 不支持、状态恢复失败；不只汇总成功任务 |
| 会话成本 | 分配 GPU 的设备秒、宿主 CPU core·s、host GiB·s、GPU framebuffer GiB·s | 分配成本和实际活动分开；GPU utilization×时间不是 GPU FLOPs |
| GPU 计算 | 工具阶段的设备活动时间线、可用时的 kernel/stream 事件、SM/计算管线活动 | 活跃区间与 kernel 时长之和分开，并行 kernel 不能重复当 wall time |
| GPU 内存 | 每设备 framebuffer used、每进程可归属用量、框架 allocated/reserved、峰值与时间积分 | framework allocated/reserved 与设备总量口径不同；不能把峰值×session时长当积分 |
| 状态持续性 | 无前台请求时的显存、后台 GPU 活动、首次后续有效结果时间 | 保留状态必须有任务用途，并安排真实后续访问 |
| 数据传输 | H2D/D2H、PCIe/NVLink、任务输入输出和 checkpoint 字节 | 写明来源、方向、单位、范围；主机链路计数不等于某任务独享流量 |
| 多卡 | rank/设备映射、collective 等待、实际互联、每卡活动与内存偏斜 | 单机多卡与跨机通信分别记录；改变 GPU 数量不是新增任务 |
| 诊断 | power/energy（可用时）、时钟、温度/限频、缺页/迁移、编译缓存 | 诊断量帮助解释结果，不强制折成统一分数 |

GPU/驱动/采集器不同，计数器支持范围也不同。缺失的计量应记为 null 和原因。先读设备能力并保存实际字段 ID、单位、时间窗口、采样频率和 provider 版本，不将另一版 DCGM 的字段名直接当成本机可用项。

## 3. 异步完成和计时

CUDA kernel launch 可以早于设备工作完成返回。工具合同应区分 command accepted、device work complete、artifact available。用应用已有完成事件、stream/event 同步或可验证结果建立依赖；不在每个 kernel 后强制全设备同步来改变原执行。

性能主运行保持轻量采集；详细 CUPTI/Nsight 或高频 profiling 作为参考画像/诊断运行，记录采集开销。实际工具 wall time 包含合理的数据加载、CPU 预处理和结果输出，kernel-only 数据单列。

## 4. 驻留、缓存与公平比较

框架内存缓存是真实的资源持有，不是虚假数字，但需要区别于活跃 tensor。GPU context、KV cache、模型权重、优化器状态和临时激活分别标注适用项。可以使用合法 CPU offload、分页、压缩、混合精度，但这些是冻结的软件配置或显式策略变量。

固定冷/热模型加载、JIT/算子编译缓存、数据加载和验证阶段。主对照不在每次 tool call 清空显存缓存。加载器的 pinned host memory、CPU worker、模型文件和 checkpoint 流量必须计入同一任务或明确的准备阶段。

共享 GPU/MIG/MPS 场景先保存设备与实例拓扑。设备总量用于容量和全局效率；不能将多个进程可见的共享量重复相加。只用独占运行校准得到的 profile 做筛选，混部后的实际需求作为结果。

## 5. 来源

- [CUDA asynchronous execution](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/asynchronous-execution.html)：异步提交与事件完成语义。
- [PyTorch CUDA semantics](https://docs.pytorch.org/docs/stable/notes/cuda)：tensor 用量与 caching allocator 管理量的区别。
- [DCGM profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)：设备活动、内存和互联计量。
- [DCGM Exporter metrics](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)：具体采集字段随版本和能力确认。
