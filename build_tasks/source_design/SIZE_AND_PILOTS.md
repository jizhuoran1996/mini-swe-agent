# 工程规模与第一批实施

六组用于组织工程生态；每组内部保留不同的构建体量。规模不是按任务名称硬分的，也不以下载仓库大小代替真实工作量。当前 `planned_scale_class` 是工程选择时的规划标签，正式大小应由 reference profile 确认。

## 每题的三档范围

| 档位 | 用途 | 必须保持 |
|---|---|---|
| core | 最小但完整有用的工程交付，适合先调通环境 | 真正源码构建、非空正式测试、独立 consumer |
| reference | 该题正式参考的声明目标与测试范围 | 输入/功能/缓存/并行配置固定，完整阶段记账 |
| extended | 扩展模块、工具链阶段、测试范围或设备编译 | 同一 canonical task，显式额外能力与验收 |

小库的 reference 仍可以小；不要为了统一持续时间加入空转或重复编译。需要更大资源需求时优先选择自然具有更多编译单元、生成器、依赖阶段或较大链接目标的工程。

任务卡的具体 recipe 默认描述 reference。启用 core 或 extended 时，builder 将该档位的目标、特性和测试变化解析到独立 instance manifest；仍须满足相应完整交付、非空官方测试和 consumer 验收，不能只改档位名称。

## 建议先做的 12 题

| 组 | 首批 | 先确认什么 |
|---|---|---|
| A | zlib、libgit2 | 标准库交付、CTest/自带测试、独立链接验证 |
| B | CPython、GNU binutils | runtime/toolchain 产物、真实官方测试及工具来源 |
| C | FFmpeg、libvips | 特性选择、媒体 fixture 和可用产物验证 |
| D | DuckDB、etcd | C++/Go 构建、本地数据库/服务消费 |
| E | TypeScript、esbuild | JS 与 native 产物、锁定工具版本、构建包消费 |
| F | NumPy、XGBoost | native wheel、来源隔离、数值功能验收 |

这 12 题的选择是实施顺序建议，不是已测时间排序。下一批推进 LLVM/Clang、OpenJDK、OpenCV、PostgreSQL、Kafka、PyTorch；最后处理更复杂的完整 bootstrap、多组件框架与 Envoy/ClickHouse 等大工程。用户希望的 PyTorch 是正式任务之一，可在上述流程跑通后直接作为大型工程样本。

## 挑选最终正式语料

先依据构建成功率和 oracle 质量确定可用实例，再依据 CPU core·s、内存峰值、workspace 峰值/持有时间、进程/metadata 和实际 I/O 选取资源分层。高并行度和大型工程都保留，但不要让某个超大 monorepo 占据大部分采样份额。需要高需求配比时显示可用的独立工程和轨迹数，重复采样显式记录。
