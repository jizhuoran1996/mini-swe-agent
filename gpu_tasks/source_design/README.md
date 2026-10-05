# 60个GPU Agent任务：来源、设计与实现说明

版本：`sandbox_gpu_60_source_based_v1`  
用途：为THENAME补充可采集、可验证、可真实回放的GPU工具执行任务。  
来源核查：2026-10-04。

## 这份包交付什么

本包给出60个具体的GPU agent任务设计，分六组，每组10个。每题都绑定了现有benchmark或官方工作流，以及实际模型、数据或配置；随后将其转换为有交付物、后续使用和独立验收的agent任务。例如，向量benchmark被转换成可保存、重载和查询的索引交付，天气模型被转换成完整集合预报与续报，图像生成被转换成可检索素材库。

本版完成来源调研、任务规格和包结构验证；尚未构建GPU环境、下载权重/完整数据或采集实测轨迹。正式资源画像和验证结果保留为空值。它适合交给实现者逐项建包，也可以先据此选择第一批要采集的GPU工作流。

## 一、六组覆盖

| 组别 | 数量 | 内容 | 主要预期资源形态 |
|---|---:|---|---|
| A · 语言、语音与推荐模型训练 | 10 | SFT、DPO、语音适配、大嵌入推荐、70B适配、BERT/DPR训练 | 全参数/适配训练、优化器与嵌入状态、checkpoint、collective |
| B · 视觉理解、分割与三维感知 | 10 | 分类、检测、实例/语义分割、医学体数据、LiDAR、视频、跟踪和深度 | 高分辨率输入、反向传播、3D张量、主机供数和产物输出 |
| C · 图像、视频、音频与三维生成 | 10 | 图像生成/补全/结构转换、视频生成/修复、音乐、音效、TTS、PBR资产 | 持续生成、大模型驻留、媒体处理与产物增长 |
| D · 任务侧模型推理与检索处理 | 10 | 长文QA/摘要、代码补全、SQL、文档/视频理解、向量、重排和翻译 | 32B/72B权重、长上下文、prefill/decode、常驻服务 |
| E · GPU数据、向量与图计算 | 10 | 大表分析、特征ETL、提升树、亿级向量、图算法、图学习 | 大表连接、图/索引驻留、host-device传输、spill及多GPU通信 |
| F · 科学机器学习与物理计算 | 10 | 宇宙学、极端天气、蛋白结构、催化、分子/材料、集合预报与物理代理 | 大物理域、多步推进、集合计算、科学状态与跨轮续跑 |

六组是组织方式，不是六个互斥的资源类别。一个任务可以同时包含显存驻留、GPU计算、CPU供数、存储写回和进程通信。`resource_shape_tags`记录设计预期；只有在固定参考配置下实测后，才能用于正式资源配比。

## 二、怎样落实“规模大”

选题优先考虑四种真实规模：较大模型及训练状态、大输入集合、高分辨率或大物理域、长期保留且被再次使用的设备状态。不是每题都要求占满80GiB显存；持续有效计算和大规模数据搬运同样有价值。

| 任务 | 本包采用的具体规模 | 设计依据/来源 |
|---|---|---|
| A07 大嵌入点击率训练 | 完整Criteo Terabyte、DLRM FL=3 large；模型checkpoint为数十GB量级 | [NVIDIA DLRM](https://github.com/NVIDIA/DeepLearningExamples/blob/master/PyTorch/Recommendation/DLRM/README.md) |
| A08 长报告模型适配 | Llama2-70B、完整GovReport、真实LoRA训练 | [MLPerf Training工作负载](https://mlcommons.org/benchmarks/training/) |
| C01 图像素材库 | 5,000个原生样本、1024×1024图像及可重载资产目录 | [MLPerf SDXL/COCO](https://docs.mlcommons.org/inference/benchmarks/text_to_image/reproducibility/scc24/) |
| C04/C05 视频生成 | Wan2.2 A14B、HunyuanVideo-I2V，720p完整场景视频 | [Wan2.2](https://github.com/Wan-Video/Wan2.2)、[HunyuanVideo-I2V](https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V) |
| D06 长视频理解 | 72B模型，900段真实视频、2,700个问题；时间轴采样预算固定 | [Video-MME](https://github.com/MME-Benchmarks/Video-MME) |
| D08 神经向量生产 | 8B编码器，MIRACL阿拉伯语+印地语约257万真实段落 | [MIRACL](https://github.com/project-miracl/miracl) |
| E01 大表处理 | PDS-H SF1000，GPU流式连接、聚合和实际结果表 | [cuDF-Polars benchmark](https://docs.nvidia.com/cudf/26.10/cudf_polars/benchmarks/) |
| E05/E06 向量索引和聚类 | 原生100M向量；1B完整规模作为扩展 | [Faiss十亿级索引](https://github.com/facebookresearch/faiss/wiki/Indexing-1G-vectors)、[cuVS](https://docs.nvidia.com/cuvs/user-guide/api-guides/clustering-guide/k-means) |
| F05 分子模拟 | 465,399原子hEGFR体系，真实物理时间推进和有状态续跑 | [HECBioSim](https://www.hecbiosim.org/access-hpc/hpc-benchmarking-suite) |
| F10 三维物理代理 | The Well原生3D湍流场；对应来源数据约744.6GB | [The Well TRL3D](https://polymathic-ai.org/the_well/datasets/turbulent_radiative_layer_3D/) |

这些是任务规模或上游来源描述，不是THENAME测得的最低显存与运行时间。大训练与完整媒体集合可能运行很久：正式实例可以按预先声明的完整输入分片或checkpoint阶段构造，但必须同步固定目标和验收，不能在目标后端临时截短。全量任务和其有限实例共享canonical task ID。

### 三档规模

| 档位 | 作用 | 使用规则 |
|---|---|---|
| Debug | 调通数据、执行入口与oracle | 小的真实子集；不作为正式“大GPU”画像 |
| Reference large | 建立正式参考轨迹 | 具体源数据范围、模型、更新数/推理协议和交付物均冻结 |
| Optional scale-out | 增大数据或多GPU | 同一任务的变体；明确分片、通信、offload及验证方式 |

卡片的T1/T2/T3分别是单张24–48GiB、单张80GiB、2–8张GPU的工程规划档位。实现时还需要主机RAM、工作盘、互联和框架兼容性准入。1B向量、大图和多卡训练不能只凭总显存容量判断可行。

## 三、为什么是agent任务

每题同时包含具体目标、真实交付物和独立oracle。Agent要完成模型或数据处理工作，产物应能被后续工具实际消费；只给benchmark分数或一份成功日志不足以完成任务。可调用官方CLI或薄适配器一次完成工作，无需人为添加bug、思考步骤或规定调用轮数。

几个典型转换如下：

- **E05**：从ANN吞吐测试变成亿级索引构建、持久化、重新加载、按真实查询返回近邻；验收检查召回、ID与实际索引状态。
- **C06**：从视频修复模型测试变成完整受损视频恢复项目；任务环境仅有受损帧，干净视频只给oracle。
- **D08**：从embedding示例变成百万级向量分片、文档ID映射和可继续调用的编码接口；验收包括真实后续请求。
- **F07**：从天气模型示例变成集合预报、区域风险摘要和后续续报；五个展示气象量之外，额外交付模型继续推进所需的完整状态与RNG状态。
- **A08**：从模型微调速度测试变成可重载adapter和长报告摘要交付；训练与任务侧验证推理都真实执行。

对于模型生成的答案、SQL和媒体，执行完整性与语义质量分别判定。固定模型不必对所有样本都预测正确；质量按参考运行校准，模型错误与OOM、超时、丢失进程、损坏文件分别报告。Oracle保留独立输入边界，也不代替agent执行主要GPU工作。

## 四、GPU回放与cloud sandbox需要保留什么

THENAME回放的是负责决策的agent LLM。任务中用于训练、embedding、视频生成或文档理解的模型仍然真实运行；不能用记录的预测或sleep替代这些GPU计算。

除了命令和文件，GPU任务还需要记录设备绑定、进程与服务句柄、真实异步完成事件和跨调用状态。权重、优化器、KV、图索引、科学状态各有生命周期；只复用文件不代表模型一直驻留。原始运行中的端口、PID、rank、job ID及设备UUID不能直接当作下一次运行的有效句柄。

建议先在已有任务上施加以下场景，它们不增加任务数量：

| 场景 | 观察什么 |
|---|---|
| 独占GPU参考 | 正确执行、参考时间和资源画像 |
| 加载与首次使用 | 数据预置后，权重加载、上下文初始化、实际ready时间 |
| 保持状态后再次访问 | 模型等待期间的显存持有、后台GPU工作、再次响应 |
| 长短任务混合与突发到达 | 准入队列、资源竞争、尾延迟与有效完成 |
| 多GPU任务 | 拓扑、collective、rank绑定、分片及资源碎片 |
| 取消与回收 | 子进程/worker清理、GPU释放、部分产物状态 |
| 应用checkpoint与恢复 | 真实状态写出/重载、重复计算及恢复后正确性 |

首版用Native+GPU与容器+GPU打通即可；gVisor的GPU路径、VM设备路径和多GPU能力按后端实际配置验收。应用checkpoint、CUDA进程checkpoint和VM快照是不同能力，不能互相替代。相关接口与记账写在`REPLAY_AND_STATE.md`、`BACKEND_CAPABILITIES.md`和`CLOUD_SCENARIOS.md`。

## 五、建议优先落地的任务

本包优先级分布为 **14个pilot、27个standard、19个advanced**。优先级是工程推进顺序，不是已测难度排序。首批可以从以下8个开始：

| ID | 先做它的理由 |
|---|---|
| B02 OpenImages目标框目录 | 发布模型、完整真实图像集合、标准检测评价与可查询产物 |
| C01 SDXL素材库 | 已有成熟推理源、持续生成和大量真实输出 |
| C06 ProPainter视频修复 | 分辨率、视频窗口和主机供数共同影响工作集 |
| D08 百万级embedding | 大量有效文本、真实向量文件和模型驻留 |
| E03 HIGGS训练 | 原生11M数据、标准GPU提升树和较容易独立验收的分类结果 |
| E05 100M ANN索引 | 大索引状态、host-device传输、持久化和再次查询 |
| F04 OC20结构弛豫 | 实际迭代GPU计算与物理停止条件，模型规模较可控 |
| F05 大型GROMACS模拟 | 独立于语言模型的成熟GPU路径、真实续跑和明确物理状态 |

随后增加A04语音适配和一条大模型训练，再扩展C04/C05视频生成、多GPU大图及科学训练。无需第一轮就把全部60题的完整生产规模跑完。

## 六、包内文件和用法

| 文件/目录 | 内容 |
|---|---|
| `README.md` | 本说明与60题总览 |
| `TASK_CATALOG.md` | 逐题来源、正式规模、优先级和任务卡入口 |
| `task_briefs/` | 60份完整实施规格，含oracle与负例 |
| `agent_prompts/` | 60份初始/后续提示模板，实例化后分阶段交付 |
| `task_registry.json`、`tasks.jsonl` | 同一批60条机器可读设计记录 |
| `sources.json`、`SOURCES.md` | 官方来源、检查位置、版本与访问条件 |
| `templates/` | 资产锁、实例、回放、运行报告及设备能力模板 |
| `GPU_ADMISSION.md` | 功能、GPU真实执行、资源形态的独立准入与记账 |
| `INSTANCE_AND_ORACLE.md` | 分片、initial/continuation、隐藏输入和数值验收 |
| `DATA_AND_SCALE.md` | 规模、数据与环境准备边界 |
| `REPLAY_AND_STATE.md` | 异步完成、句柄绑定、设备状态与恢复 |
| `CLOUD_SCENARIOS.md` | GPU云场景，不作为额外task IDs |
| `BACKEND_CAPABILITIES.md` | 后端设备能力和比较范围 |
| `DEDUP_AND_LINEAGE.md` | 与已有CPU/Memory/I/O任务的关系及去重 |
| `CODEX_HANDOFF.md` | 从设计到采集/回放/准入的实施步骤 |
| `KNOWN_GAPS.md` | 本版尚需完成的构建和实测工作 |
| `validate_plan.py`、`VALIDATION_REPORT.json` | 结构一致性校验器与本次结果 |
| `render_views.py` | 从registry重新生成卡片、目录与JSONL |
| `CHECKSUMS.sha256` | 发布文件校验和 |

解压后，在包目录运行：

```bash
python3 validate_plan.py --self-check
```

修改registry后可以运行`python3 render_views.py --root .`更新派生视图，再重新校验。构建后将`readiness.stage`推进并写入对应证据文件及哈希；校验器允许从design前进，不会强制永远保持未构建。结构通过不等于GPU任务运行通过。

## 七、60题简表

### A · 语言、语音与推荐模型训练

| ID | 任务 |
|---|---|
| GPUv1-A01 | 训练可交付的多轮指令对话模型 |
| GPUv1-A02 | 训练并验证偏好对齐后的对话模型 |
| GPUv1-A03 | 构建可离线交付的英德机器翻译模型 |
| GPUv1-A04 | 适配大规模语音转写模型并交付转录结果 |
| GPUv1-A05 | 训练英语语音到德语文本的翻译模型 |
| GPUv1-A06 | 用大规模无标注音频扩展语音表示模型 |
| GPUv1-A07 | 训练并交付大表嵌入的点击率模型 |
| GPUv1-A08 | 适配70B长报告摘要模型并交付可复用适配器 |
| GPUv1-A09 | 训练问答检索双编码器并交付检索表征 |
| GPUv1-A10 | 从完整百科语料训练通用文本编码器 |

### B · 视觉理解、分割与三维感知

| ID | 任务 |
|---|---|
| GPUv1-B01 | 训练并交付 ImageNet 图像分类模型 |
| GPUv1-B02 | 为开放图像库建立可查询的目标框目录 |
| GPUv1-B03 | 训练 COCO 实例分割与对象轮廓导出 |
| GPUv1-B04 | 建立高分辨率城市道路语义分割模型 |
| GPUv1-B05 | 生成三维肾脏肿瘤分割与体积结果 |
| GPUv1-B06 | 训练驾驶场景三维目标检测并交付空间框 |
| GPUv1-B07 | 训练点云语义分类并交付完整扫描标签 |
| GPUv1-B08 | 微调视频动作识别并输出片段目录 |
| GPUv1-B09 | 训练单目标跟踪器并生成连续轨迹 |
| GPUv1-B10 | 训练户外米制深度模型并导出三维点云 |

### C · 图像、视频、音频与三维生成

| ID | 任务 |
|---|---|
| GPUv1-C01 | 批量生成可检索的高分辨率图像素材库 |
| GPUv1-C02 | 完成带掩码图片并保留未编辑区域 |
| GPUv1-C03 | 保持场景布局的图像风格转换 |
| GPUv1-C04 | 从场景脚本生成完整视频素材库 |
| GPUv1-C05 | 将静态素材制作成保持主体的动态镜头 |
| GPUv1-C06 | 恢复高分辨率视频的缺失区域 |
| GPUv1-C07 | 根据旋律和描述生成音乐素材 |
| GPUv1-C08 | 制作可检索的环境声音素材库 |
| GPUv1-C09 | 构建保持参考音色的中英语音素材库 |
| GPUv1-C10 | 从单张参考图制作可渲染的 PBR 三维资产 |

### D · 任务侧模型推理与检索处理

| ID | 任务 |
|---|---|
| GPUv1-D01 | 部署科研论文阅读服务并生成逐题答案档案 |
| GPUv1-D02 | 把政府报告语料编成可更新的摘要档案 |
| GPUv1-D03 | 为代码库上下文建立可调用的跨文件补全工具 |
| GPUv1-D04 | 部署自然语言数据库查询工具并交付真实结果表 |
| GPUv1-D05 | 把文档图像问题转成可检索的答案台账 |
| GPUv1-D06 | 建立长视频内容问答目录 |
| GPUv1-D07 | 将混合版式文档解析为可再利用的结构化档案 |
| GPUv1-D08 | 为百万级多语言语料生产可更新的语义向量 |
| GPUv1-D09 | 把检索候选重排为可复查的证据列表 |
| GPUv1-D10 | 交付多语言文档翻译包并提供后续翻译接口 |

### E · GPU数据、向量与图计算

| ID | 任务 |
|---|---|
| GPUv1-E01 | 构建大规模订单收入与履约分析数据集 |
| GPUv1-E02 | 生成历史房贷逾期特征仓库 |
| GPUv1-E03 | 训练完整 HIGGS 事件分类模型 |
| GPUv1-E04 | 构建年度出租车费用回归与审计模型 |
| GPUv1-E05 | 构建亿级图像描述子检索索引 |
| GPUv1-E06 | 为大型视觉向量库生成内容分区 |
| GPUv1-E07 | 生成大型历史关注图的节点优先级报告 |
| GPUv1-E08 | 建立全量 Friendster 社区与跨社区连接清单 |
| GPUv1-E09 | 训练异构学术图的主题分类器 |
| GPUv1-E10 | 训练缺失引用推荐模型 |

### F · 科学机器学习与物理计算

| ID | 任务 |
|---|---|
| GPUv1-F01 | 从宇宙密度体数据训练参数回归模型 |
| GPUv1-F02 | 建立大气河流与热带气旋识别模型 |
| GPUv1-F03 | 为长蛋白目标构建可复核的结构预测集 |
| GPUv1-F04 | 完成催化吸附初态弛豫与能量排序 |
| GPUv1-F05 | 推进大型膜蛋白体系并交付动力学分析 |
| GPUv1-F06 | 模拟金属晶体并分析有限温度结构稳定性 |
| GPUv1-F07 | 生成全球天气集合预报及区域风险摘要 |
| GPUv1-F08 | 将粗分辨率天气数据降尺度为区域集合场 |
| GPUv1-F09 | 训练车辆外流场代理并交付阻力预测 |
| GPUv1-F10 | 预测三维湍流混合层并验证多步演化 |

## 八、计数和后续研究范围

60表示任务设计数，不表示60种完全不同算法、60个独立原始benchmark或已采集60条轨迹。训练/推理可能共享数据；GPU向量、图或表处理也可能与此前Memory/I/O包共享应用目标。相同目标和输入的CPU/GPU实现应作为同一canonical任务的后端变体，合并语料时保留family与data lineage。

这一批聚焦GPU。大型工程从头构建，以及sandbox内部服务的部署、修改和外部验收，仍可作为后续独立任务包。此处的模型服务用于覆盖GPU状态及后续请求，不替代完整服务工程任务覆盖。
