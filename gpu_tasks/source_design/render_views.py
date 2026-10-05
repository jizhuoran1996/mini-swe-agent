#!/usr/bin/env python3
"""Assemble or re-render the GPU design pack using Python's standard library."""
import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

GROUPS = {
    'A': ('语言、语音与推荐模型训练', '全参数/适配训练、优化器与嵌入状态、checkpoint、collective'),
    'B': ('视觉理解、分割与三维感知', '高分辨率输入、反向传播、3D张量、主机供数和产物输出'),
    'C': ('图像、视频、音频与三维生成', '持续生成、大模型驻留、媒体处理与产物增长'),
    'D': ('任务侧模型推理与检索处理', '32B/72B权重、长上下文、prefill/decode、常驻服务'),
    'E': ('GPU数据、向量与图计算', '大表连接、图/索引驻留、host-device传输、spill及多GPU通信'),
    'F': ('科学机器学习与物理计算', '大物理域、多步推进、集合计算、科学状态与跨轮续跑'),
}
LINEAGE = {
    'A': ['ultrachat_200k','ultrafeedback_binarized','wmt16_en_de','librispeech','covost2_en_de','libri_light','criteo_terabyte','scrolls_gov_report','natural_questions_dpr','wikipedia_20231101_en'],
    'B': ['imagenet_ilsvrc2012','openimages_v6','coco2017','cityscapes','kits19','nuscenes','semantic_kitti','something_something_v2','got10k','virtual_kitti2_and_kitti'],
    'D': ['qasper_longbench','gov_report_longbench','repobench_p_longbench','bird_sql_dev_20251106','docvqa','video_mme','omnidocbench','miracl_ar_hi','beir_natural_questions','wmt24pp'],
}
MEASUREMENTS = [
    'gpu_count','session_wall_s','tool_active_wall_s','gpu_allocated_device_s',
    'device_memory_peak_gib','device_memory_integral_gib_s','host_cpu_core_s',
    'host_memory_integral_gib_s','workspace_peak_gib','h2d_bytes','d2h_bytes','inter_gpu_bytes'
]
EVIDENCE_KEYS = ['asset_lock','environment_lock','implementation_manifest','oracle_report','trajectory_manifest','replay_report','reference_profile','admission_report']


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def plain(value):
    if isinstance(value, dict):
        return '；'.join(f'{k}: {plain(v)}' for k, v in value.items())
    if isinstance(value, list):
        return '；'.join(plain(v) for v in value)
    if value is None:
        return 'null'
    return str(value)


def block(value):
    if isinstance(value, dict):
        return '\n'.join(f'- **{k}**：{plain(v)}' for k, v in value.items())
    if isinstance(value, list):
        return '\n'.join('- ' + plain(v) for v in value)
    return str(value)


def table_cell(value):
    return plain(value).replace('|', '\\|').replace('\n', ' ')


def source_links(task, source_map):
    return '\n'.join(
        f'- [{sid}] {source_map[sid]["title"]} — [来源]({source_map[sid]["url"]})；检查位置：{source_map[sid]["inspected_unit"]}'
        for sid in task['source_ids']
    )


def card_text(task, source_map):
    header = f'# {task["id"]} · {task["title_zh"]}\n\n{task["title_en"]}\n\n'
    header += f'**组别**：{GROUPS[task["group"]][0]}　 **实施优先级**：{task["implementation_priority"]}　 **阶段**：{task["readiness"]["stage"]}\n\n'
    header += f'**Canonical goal**：`{task["canonical_goal_key"]}`\n\n**Workflow family**：`{task["workflow_family"]}`\n\n'
    sections = [
        ('任务目标',task['agent_goal']), ('具体来源工作负载',task['source_task_or_workload']),
        ('输入与配置',task['inputs']),('需要完成的工作',task['required_work']),
        ('交付物',task['deliverables']),('后续使用与状态',task['continuation']),
        ('独立验收',task['oracle']),('应拒绝的失败方式',task['negative_cases']),
    ]
    text = header
    for title, value in sections:
        text += f'## {title}\n\n{block(value)}\n\n'
    text += '## 规模配方\n\n'
    for key, label in [('debug','Debug：仅调通'),('reference_large','Reference large：正式生产规模'),('optional_scale_out','可选扩展：同一任务的变体')]:
        text += f'### {label}\n\n{block(task["scale_plan"][key])}\n\n'
    for title, key in [
        ('GPU工作与预期资源形态','gpu_rationale'),('资源标签（待画像验证）','resource_shape_tags'),
        ('设备能力','gpu_capabilities'),('后端要求','backend_requirements'),('回放约束','replay_notes'),
        ('Builder需要实现的部分','new_builder_work'),('与相关任务的边界','distinct_from_related_tasks'),
        ('数据血缘','data_lineage'),('任务范围与条件','limitations'),
    ]:
        text += f'## {title}\n\n{block(task[key])}\n\n'
    for key, title in [('input_visibility','输入可见范围'),('oracle_scope','验收范围')]:
        if key in task:
            text += f'## {title}\n\n{block(task[key])}\n\n'
    text += '## 来源记录\n\n' + source_links(task, source_map) + '\n\n'
    text += '资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。\n'
    return text


def prompt_text(task):
    return (
        f'# {task["id"]} · Agent任务提示模板\n\n'
        'Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。\n\n'
        f'## 初始任务\n\n{task["agent_goal"]}\n\n'
        f'### 来源和工作范围\n\n{task["source_task_or_workload"]}\n\n'
        f'### 交付要求\n\n{block(task["deliverables"])}\n\n'
        f'### 必须完成的工作\n\n{block(task["required_work"])}\n\n'
        '请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。\n\n'
        f'## 后续请求（依实际依赖单独发出）\n\n{task["continuation"]}\n\n'
        '如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。\n'
    )


def catalog_text(tasks, source_map):
    out = '# GPU任务目录：60个来源派生设计\n\n每行是一个canonical task。规模与GPU配置是拟构建配方，不是已测门槛。点击ID查看完整任务卡；卡片中的来源链接对应具体实现或数据。\n\n'
    for group, (title, shape) in GROUPS.items():
        out += f'## {group} · {title}\n\n{shape}。\n\n'
        out += '| ID | Agent交付目标 | 具体来源 | 正式规模 | 优先级 |\n|---|---|---|---|---|\n'
        for t in tasks:
            if t['group'] != group:
                continue
            scale = t['scale_plan']['reference_large']
            scale_display = {k:v for k,v in scale.items() if k not in ('status','measured_requirement','useful_output','output')}
            out += f'| [{t["id"]}](task_briefs/{t["id"]}.md) | {table_cell(t["title_zh"])} | {table_cell(t["source_task_or_workload"])} | {table_cell(scale_display)} | {t["implementation_priority"]} |\n'
        out += '\n'
    return out


def render_views(root, registry, sources):
    tasks = registry['tasks']
    source_map = {s['id']:s for s in sources['sources']}
    for folder in ('task_briefs','agent_prompts'):
        (root/folder).mkdir(parents=True,exist_ok=True)
    for t in tasks:
        (root/t['task_brief_path']).write_text(card_text(t,source_map),encoding='utf-8')
        (root/t['agent_prompt_path']).write_text(prompt_text(t),encoding='utf-8')
    (root/'tasks.jsonl').write_text(''.join(json.dumps(t,ensure_ascii=False)+'\n' for t in tasks),encoding='utf-8')
    (root/'TASK_CATALOG.md').write_text(catalog_text(tasks,source_map),encoding='utf-8')
    body = '# 主要来源与检查位置\n\n来源核查日期：2026-10-04。这里记录页面、实现和数据的定位；模型、数据、源码及评价器的不可变内容锁定在实例构建阶段完成。相同URL的多条记录可能服务不同组，不代表不同benchmark。\n\n'
    for s in sources['sources']:
        body += f'## {s["id"]} · {s["title"]}\n\n'
        body += f'- URL：[{s["url"]}]({s["url"]})\n- 发布者：{s["publisher"]}\n- 检查位置：{s["inspected_unit"]}\n- 支持的来源事实：{s["supports"]}\n- 浏览/文档版本：{s["inspected_ref"]}\n- 不可变revision：{plain(s["pinned_revision"])}\n- 资产许可/访问状态：{s["asset_license_status"]}\n\n'
    (root/'SOURCES.md').write_text(body,encoding='utf-8')


def overview(registry, sources):
    tasks = registry['tasks']
    priorities = Counter(t['implementation_priority'] for t in tasks)
    out = '''# 60个GPU Agent任务：来源、设计与实现说明

版本：`sandbox_gpu_60_source_based_v1`  
用途：为THENAME补充可采集、可验证、可真实回放的GPU工具执行任务。  
来源核查：2026-10-04。

## 这份包交付什么

本包给出60个具体的GPU agent任务设计，分六组，每组10个。每题都绑定了现有benchmark或官方工作流，以及实际模型、数据或配置；随后将其转换为有交付物、后续使用和独立验收的agent任务。例如，向量benchmark被转换成可保存、重载和查询的索引交付，天气模型被转换成完整集合预报与续报，图像生成被转换成可检索素材库。

本版完成来源调研、任务规格和包结构验证；尚未构建GPU环境、下载权重/完整数据或采集实测轨迹。正式资源画像和验证结果保留为空值。它适合交给实现者逐项建包，也可以先据此选择第一批要采集的GPU工作流。

## 一、六组覆盖

| 组别 | 数量 | 内容 | 主要预期资源形态 |
|---|---:|---|---|
'''
    examples = {
        'A':'SFT、DPO、语音适配、大嵌入推荐、70B适配、BERT/DPR训练',
        'B':'分类、检测、实例/语义分割、医学体数据、LiDAR、视频、跟踪和深度',
        'C':'图像生成/补全/结构转换、视频生成/修复、音乐、音效、TTS、PBR资产',
        'D':'长文QA/摘要、代码补全、SQL、文档/视频理解、向量、重排和翻译',
        'E':'大表分析、特征ETL、提升树、亿级向量、图算法、图学习',
        'F':'宇宙学、极端天气、蛋白结构、催化、分子/材料、集合预报与物理代理',
    }
    for group, (title, shape) in GROUPS.items():
        out += f'| {group} · {title} | 10 | {examples[group]} | {shape} |\n'
    out += '''
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

'''
    out += f'本包优先级分布为 **{priorities["pilot"]}个pilot、{priorities["standard"]}个standard、{priorities["advanced"]}个advanced**。优先级是工程推进顺序，不是已测难度排序。首批可以从以下8个开始：\n\n'
    out += '''| ID | 先做它的理由 |
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

'''
    for group, (title, _) in GROUPS.items():
        out += f'### {group} · {title}\n\n| ID | 任务 |\n|---|---|\n'
        for t in tasks:
            if t['group'] == group:
                out += f'| {t["id"]} | {t["title_zh"]} |\n'
        out += '\n'
    out += '''## 八、计数和后续研究范围

60表示任务设计数，不表示60种完全不同算法、60个独立原始benchmark或已采集60条轨迹。训练/推理可能共享数据；GPU向量、图或表处理也可能与此前Memory/I/O包共享应用目标。相同目标和输入的CPU/GPU实现应作为同一canonical任务的后端变体，合并语料时保留family与data lineage。

这一批聚焦GPU。大型工程从头构建，以及sandbox内部服务的部署、修改和外部验收，仍可作为后续独立任务包。此处的模型服务用于覆盖GPU状态及后续请求，不替代完整服务工程任务覆盖。
'''
    return out


def templates(root):
    folder = root/'templates'
    folder.mkdir(exist_ok=True)
    write_json(folder/'asset_lock.template.json', {
        'schema_version':'gpu-assets-v1','status':'template','task_id':None,'instance_id':None,
        'assets':[{'kind':'model_or_dataset_or_code_or_evaluator','source_id':None,'canonical_url':None,'immutable_revision':None,'sha256':None,'bytes':None,'local_relative_path':None,'split':None,'selected_ids_manifest':None,'license_or_access_status':None,'visibility':'agent_input_or_oracle_only'}],
        'input_partition':{'initial_ids_manifest':None,'continuation_ids_manifest':None,'repeat_ids_manifest':None,'unique_count':None},
        'environment':{'image_digest':None,'driver':None,'cuda':None,'framework':None,'source_commits':None},
        'preparation':{'weights_prepositioned':None,'data_preprocessed':None,'timed_in_task':None}
    })
    write_json(folder/'instance.template.json', {
        'schema_version':'gpu-instance-v1','status':'template','task_id':None,'instance_id':None,
        'canonical_goal_key':None,'data_lineage':[],'scale_profile':'reference_large','asset_lock_sha256':None,
        'initial_prompt_path':None,'continuation_prompt_path':None,'resolved_workload_config':None,
        'required_unique_inputs':None,'training_update_budget':None,'inference_config':None,'physical_steps':None,
        'gpu_request':{'count':None,'memory_per_device_gib':None,'precision':None,'topology':None,'sharing_mode':None},
        'host_budget':{'cpu_cores':None,'memory_gib':None,'workspace_gib':None,'shared_memory_gib':None},
        'state_contract':{'retained_objects':[],'application_checkpoint':None,'continuation_completion_rule':None},
        'oracle':{'implementation_hash':None,'hidden_reference_hash':None,'integrity_rules':None,'quality_gate':None,'numerical_tolerance':None},
        'execution_limits':{'session_timeout_s':None,'cancel_grace_s':None,'drain_cutoff_s':None}
    })
    write_json(folder/'replay_manifest.template.json', {
        'schema_version':'gpu-replay-v1','status':'template','corpus_version':None,'reference_profile_version':None,
        'instance_manifest_sha256':None,'trace_id':None,'trace_sha256':None,'planned_arrival_offset_s':None,
        'model_wait_scale':1.0,'preserve_dependencies':True,'task_side_gpu_compute':'real',
        'commands':[],'dependency_edges':[],'recorded_agent_turns':[],
        'runtime_bindings':{'logical_gpu_ids':[],'logical_service_ids':[],'logical_job_ids':[],'rank_map':[]},
        'input_partition':{'initial':[],'continuation':[],'repeat':[]},
        'lifecycle_scenario':None,'cache_and_offload_policy':None,'checkpoint_contract':None,
        'finish_conditions':{'async_completion_event_required':True,'service_ready_rule':None,'artifact_commit_rule':None}
    })
    write_json(folder/'run_report.template.json', {
        'schema_version':'gpu-report-v1','status':'template','run_id':None,'task_id':None,'instance_id':None,
        'manifest_sha256':None,'backend':None,'host_configuration':None,'gpu_configuration':None,
        'events_path':None,'counter_samples_path':None,
        'outcome':{'execution_integrity':None,'semantic_quality':None,'resource_admission':None,'unsupported_reason':None,'expected_model_errors':None,'unexpected_execution_errors':None,'uncompleted_inputs':None},
        'reference_measurements':{k:None for k in MEASUREMENTS},
        'counter_provenance':{'provider':None,'provider_version':None,'device_scope':None,'field_mapping':None,'sample_period_s':None,'missing_counter_reasons':None},
        'timing':{'planned_arrival':None,'admitted':None,'sandbox_ready':None,'device_ready':None,'first_use':None,'task_complete':None,'sandbox_released':None},
        'verification_cost':{'host_cpu_core_s':None,'gpu_device_s':None},'artifacts':[]
    })
    write_json(folder/'backend_capabilities.template.json', {
        'schema_version':'gpu-capabilities-v1','status':'template','backend_name':None,'backend_version':None,
        'device_path':None,'host_driver':None,'gpu_models':None,
        'capabilities':{k:None for k in ['cuda','bf16','multi_gpu','nccl','p2p','shared_memory','pinned_host_memory','ipc','graphics_rendering','video_codec','mig','mps','application_checkpoint','gpu_process_checkpoint','vm_snapshot_with_live_gpu']},
        'capability_evidence':{},'unsupported_capabilities':{},'notes':[]
    })
    (folder/'README.md').write_text('''# 实例化模板

模板中的null由实际构建与运行填充，不是可执行的默认配置。任务来源已在registry绑定；每次实例需要另外冻结输入ID、不可变版本、真实资产哈希、oracle和资源配置。

- `asset_lock.template.json`：按模型、数据、代码、评价器分别锁定；agent输入与oracle-only资产分开。
- `instance.template.json`：冻结工作量、初始/后续提示、设备预算、状态与质量规则。
- `replay_manifest.template.json`：记录轨迹身份、计划到达、真实工具依赖及每轮动态绑定。
- `run_report.template.json`：保留执行完整性、质量、资源准入和主机/设备记账。
- `backend_capabilities.template.json`：逐项实际验证；null表示未验证，不能当false或true。

GPU完成、服务ready与产物提交应有明确事件，不能仅依据Bash命令返回或固定sleep推定。字段provider/version/scope/units用于区分框架内存、设备显存和采样计数器。模板不规定某一版DCGM字段名。
''',encoding='utf-8')


def build(group_dir, root):
    root.mkdir(parents=True,exist_ok=True)
    records, all_sources, notes = [], [], {}
    for group in GROUPS:
        d = json.loads((group_dir/f'group_{group}.json').read_text(encoding='utf-8'))
        notes[group] = d.get('notes', [])
        for s in d['sources']:
            s = dict(s)
            s.pop('citation_ref', None)
            all_sources.append(s)
        for task in d['tasks']:
            t = dict(task)
            t['group'] = group
            t['scale_plan'] = {
                key: value if isinstance(value,dict) else {'workload':value}
                for key,value in t['scale_plan'].items()
            }
            index = int(t['id'][-2:])-1
            t.setdefault('data_lineage',[LINEAGE.get(group,['source_bound']*10)[index]])
            t['readiness'] = {'stage':'design','evidence':{k:None for k in EVIDENCE_KEYS}}
            t['reference_measurements'] = {k:None for k in MEASUREMENTS}
            t['agent_prompt_path'] = f'agent_prompts/{t["id"]}.md'
            t['task_brief_path'] = f'task_briefs/{t["id"]}.md'
            t['resource_tags_status'] = 'expected_unmeasured'
            records.append(t)
    records.sort(key=lambda t:t['id'])
    all_sources.sort(key=lambda s:s['id'])
    registry = {'metadata':{
        'schema_version':'gpu-task-design-v1','package_version':'sandbox_gpu_60_source_based_v1',
        'created_on':'2026-10-04','task_count':len(records),
        'counting_unit':'canonical_task_design','stage_at_release':'design',
        'source_binding_scope':'concrete upstream workload and source inspected; immutable assets pinned at build',
        'resource_values_scope':'unmeasured values are null; hardware tiers are engineering targets',
        'group_notes':notes,
    },'tasks':records}
    sources = {'metadata':{'inspected_on':'2026-10-04','source_record_count':len(all_sources),'unique_url_count':len({s['url'] for s in all_sources})},'sources':all_sources}
    write_json(root/'task_registry.json',registry)
    write_json(root/'sources.json',sources)
    for p in (group_dir/'common_docs').glob('*.md'):
        shutil.copy2(p,root/p.name)
    shutil.copy2(group_dir/'validate_plan.py',root/'validate_plan.py')
    shutil.copy2(Path(__file__),root/'render_views.py')
    render_views(root,registry,sources)
    (root/'README.md').write_text(overview(registry,sources),encoding='utf-8')
    templates(root)
    (root/'STRUCTURE.md').write_text('''# 机器可读结构

`task_registry.json`是主记录，顶层为metadata和tasks；`tasks.jsonl`逐行保存同一批完整task对象。`sources.json`顶层为metadata和sources，使用source ID引用。可重复URL保留在不同来源记录中；统计上不能视为独立benchmark。

## Task字段

- 身份：id、group、title_zh/title_en、canonical_goal_key、workflow_family、data_lineage。
- 来源：source_task_or_workload、source_ids、derivation_kind。
- 任务合同：agent_goal、inputs、required_work、deliverables、continuation、oracle、negative_cases。
- 规模：scale_plan.debug/reference_large/optional_scale_out；每档为可扩展对象，完整说明数据、模型/计算和工程设备目标。
- 系统条件：gpu_rationale、resource_shape_tags、gpu_capabilities、backend_requirements、replay_notes。
- 实施：new_builder_work、distinct_from_related_tasks、implementation_priority、limitations。
- 证据：readiness.stage、readiness.evidence；reference_measurements中的未知实测值为null。
- 视图：agent_prompt_path、task_brief_path；部分任务增加input_visibility和oracle_scope。

## 状态前进

`design → built → verified → replayed → profiled → resource_admitted`。

各阶段需要累计证据：built需要asset_lock/environment_lock/implementation_manifest；verified增加oracle_report；replayed增加trajectory_manifest/replay_report；profiled增加reference_profile及必要实测值；resource_admitted增加admission_report。证据字段填`{"path":"evidence/file.json","sha256":"实际64位十六进制哈希"}`，路径相对包根。必须存在真实文件并匹配hash。校验器只检查证据结构和身份，不能替人判断结果的科学有效性。

修改主记录后运行`python3 render_views.py --root .`再运行`python3 validate_plan.py --self-check`。README和发布报告描述本次版本，后续新发布时需同步更新并重生成校验和。
''',encoding='utf-8')
    return registry,sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--from-groups',type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.from_groups:
        registry,sources = build(args.from_groups.resolve(),root)
    else:
        registry = json.loads((root/'task_registry.json').read_text(encoding='utf-8'))
        sources = json.loads((root/'sources.json').read_text(encoding='utf-8'))
        render_views(root,registry,sources)
    print(json.dumps({'root':str(root),'tasks':len(registry['tasks']),'sources':len(sources['sources'])},ensure_ascii=False))


if __name__ == '__main__':
    main()
