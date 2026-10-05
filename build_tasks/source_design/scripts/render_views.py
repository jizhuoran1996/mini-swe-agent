#!/usr/bin/env python3
"""Assemble or regenerate a source-grounded engineering build task pack."""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

GROUPS = {
    'A': ('原生基础库与命令行工具', '配置探测、短编译动作、静态/共享库与基础测试'),
    'B': ('编译工具链与语言运行时', 'bootstrap、代码生成、大型链接与工具链测试'),
    'C': ('多媒体、图形与地理计算工程', '模块/插件组合、原生依赖、资产与无头测试'),
    'D': ('数据库与基础设施软件', '本地服务测试、进程/文件活动和临时状态'),
    'E': ('JVM 与 JavaScript 工程', '依赖图、代码生成、包交付与运行时测试'),
    'F': ('机器学习与数值计算框架', '混合语言 native 编译、框架链接与 wheel/库交付'),
}
SIZE_NAMES = {'small':'小型','medium':'中型','large':'大型','very_large':'超大型'}
MEASUREMENTS = [
    'session_wall_s','tool_active_wall_s','host_cpu_core_s',
    'host_memory_peak_gib','host_memory_integral_gib_s',
    'workspace_peak_gib','workspace_integral_gib_s',
    'task_logical_read_bytes','task_logical_write_bytes',
    'task_block_read_bytes','task_block_write_bytes',
    'process_creations','peak_live_processes','peak_open_fds','peak_workspace_files',
    'compiled_action_count','test_executed_count',
]
EVIDENCE_KEYS = [
    'source_dependency_lock','environment_lock','implementation_manifest',
    'oracle_report','trajectory_manifest','replay_report','reference_profile',
]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def plain(value):
    if isinstance(value,dict):
        return '；'.join(f'{k}: {plain(v)}' for k,v in value.items())
    if isinstance(value,list):
        return '；'.join(plain(v) for v in value)
    return 'null' if value is None else str(value)


def block(value, depth=0):
    if isinstance(value,dict):
        return '\n'.join(f'- **{key}**：{plain(v)}' for key,v in value.items())
    if isinstance(value,list):
        return '\n'.join('- '+plain(v) for v in value)
    return str(value)


def cell(value):
    return plain(value).replace('|','\\|').replace('\n',' ')


def recipe_text(recipe):
    labels={'working_directory':'工作目录','configure':'Configure / Generate','build':'Build','package':'Package / Install','test':'Official Tests'}
    out=''
    for key,value in recipe.items():
        out+=f'### {labels.get(key,key)}\n\n'
        entries=value if isinstance(value,list) else [value]
        for entry in entries:
            line=plain(entry)
            if re_command(line):
                out+='```bash\n'+line+'\n```\n\n'
            else:
                out+='- '+line+'\n\n'
    return out.rstrip()


def re_command(line):
    # Only label a recipe as shell code when it has no prose or template syntax.
    import re
    if re.search('[\\u3400-\\u9fff]',line) or '<' in line or '>' in line:
        return False
    return line.startswith(chr(34)+'$') or bool(re.match(r'^(?:[A-Z_]+=[^ ]+ )*(?:cmake|ctest|make|ninja|meson|python3?|bazel|scons|npm|pnpm|yarn|cargo|go|\\./|"\\$)',line))


def source_links(task, source_map):
    return '\n'.join(f'- [{sid}] [{source_map[sid]["title"]}]({source_map[sid]["url"]}) — 检查位置：{source_map[sid]["inspected_unit"]}' for sid in task['source_ids'])


def card_text(t, source_map):
    text = f'# {t["id"]} · {t["title_zh"]}\n\n{t["title_en"]}\n\n'
    text += f'**主工程**：[{t["project"]}]({t["upstream_repo"]})  \n'
    text += f'**组别**：{GROUPS[t["group"]][0]}　**规划规模**：{SIZE_NAMES[t["planned_scale_class"]]}　**实施优先级**：{t["implementation_priority"]}\n\n'
    text += f'**语言**：{plain(t["language_stack"])}  \n**构建系统**：{plain(t["build_system"])}  \n**Canonical goal**：`{t["canonical_goal_key"]}`\n\n'
    for title,key in [
        ('Agent 任务目标','agent_goal'),('官方工作流与派生方式','source_task_or_workflow'),
        ('初始环境','initial_state'),('需要完成的工作','required_work'),('目标范围','target_scope'),
        ('构建与测试入口','build_recipe'),('官方测试选择','test_selection'),
        ('独立消费者验收','consumer_verification'),('交付物','deliverables'),
        ('后续使用','continuation'),('可选增量变化','incremental_variant'),
    ]:
        content=recipe_text(t[key]) if key=='build_recipe' else block(t[key])
        text += f'## {title}\n\n{content}\n\n'
    text += '## 同一任务的规模配置\n\n'
    for profile,label in [('core','Core：最小完整交付'),('reference','Reference：正式参考配置'),('extended','Extended：扩展范围')]:
        text += f'### {label}\n\n{block(t["scale_plan"][profile])}\n\n'
    for title,key in [
        ('可控变量','resource_controls'),('预期资源形态','resource_shape_tags'),
        ('后端能力要求','backend_requirements'),('离线依赖准备','offline_dependency_plan'),
        ('回放与状态','replay_notes'),('最终 oracle','oracle'),('应拒绝的负例','negative_cases'),
        ('Builder 实施工作','new_builder_work'),('源码血缘','source_lineage'),
        ('与已有任务的关系','related_prior_tasks'),('范围说明','limitations'),
    ]:
        text += f'## {title}\n\n{block(t[key])}\n\n'
    text += '## 官方来源\n\n'+source_links(t,source_map)+'\n\n'
    text += f'任务阶段：`{t["readiness"]["stage"]}`。统一构建场景、测试验收和记账口径分别见 [BUILD_SCENARIOS.md](../BUILD_SCENARIOS.md)、[TEST_AND_ORACLE.md](../TEST_AND_ORACLE.md) 和 [MEASUREMENT.md](../MEASUREMENT.md)。\n'
    return text


def prompt_text(t):
    return (
        f'# {t["id"]} · Agent 提示模板\n\n'
        'Builder 在采集前补入冻结的 source/config/test manifest、可见输入路径、可用工具链和资源预算。初始请求与可选后续请求按真实依赖分阶段提供。\n\n'
        f'## 初始请求\n\n{t["agent_goal"]}\n\n'
        f'### 提供的环境\n\n{block(t["initial_state"])}\n\n'
        f'### 工程范围\n\n{block(t["target_scope"])}\n\n'
        f'### 工作要求\n\n{block(t["required_work"])}\n\n'
        f'### 交付\n\n{block(t["deliverables"])}\n\n'
        '请使用提供的源码和依赖，在任务范围内真实构建并保存交付物。按照冻结的测试规格运行测试，保留实际结果、失败与日志。不得用预装同名软件、发布版二进制或空测试替代要求的构建和验证。允许使用官方构建工具与项目脚本，不限制解决过程的工具调用数量。\n\n'
        f'## 可选后续请求\n\n{plain(t["continuation"])}\n\n'
        '如启用增量场景，builder 另外提供该任务卡指定并完成绑定的配置变化/补丁及验收要求；它仍属于同一个任务 ID。\n'
    )


def catalog_text(tasks):
    out = '# 60 个工程构建与测试任务\n\n每个 ID 代表一个主工程交付目标。规模为规划标签；完整命令、测试选择和可选配置见任务卡。\n\n'
    for group,(title,shape) in GROUPS.items():
        out += f'## {group} · {title}\n\n{shape}。\n\n'
        out += '| ID | 主工程与交付 | 构建系统 | 规划规模 |\n|---|---|---|---|\n'
        for t in tasks:
            if t['group']==group:
                out += f'| [{t["id"]}](task_briefs/{t["id"]}.md) | {cell(t["title_zh"])} | {cell(t["build_system"])} | {SIZE_NAMES[t["planned_scale_class"]]} |\n'
        out += '\n'
    return out


def render_views(root,registry,sources):
    tasks=registry['tasks']
    sm={s['id']:s for s in sources['sources']}
    for name in ('task_briefs','agent_prompts'):
        (root/name).mkdir(exist_ok=True)
    for t in tasks:
        (root/t['task_brief_path']).write_text(card_text(t,sm),encoding='utf-8')
        (root/t['agent_prompt_path']).write_text(prompt_text(t),encoding='utf-8')
    (root/'tasks.jsonl').write_text(''.join(json.dumps(t,ensure_ascii=False)+'\n' for t in tasks),encoding='utf-8')
    (root/'TASK_CATALOG.md').write_text(catalog_text(tasks),encoding='utf-8')
    out='# 官方来源和检查位置\n\n核查日期：2026-10-05。源码与文档的检查版本逐项记录；可执行实例进一步冻结内容 hash。相同 URL 的多条检查记录不计为不同工程。\n\n'
    for s in sources['sources']:
        out += f'## {s["id"]} · {s["title"]}\n\n'
        for label,key in [('发布者','publisher'),('检查位置','inspected_unit'),('支持内容','supports'),('检查版本','inspected_ref'),('不可变 revision','pinned_revision'),('许可/访问','license_or_access_status')]:
            out += f'- {label}：{plain(s.get(key))}\n'
        out += f'- 来源：[{s["url"]}]({s["url"]})\n\n'
    (root/'SOURCES.md').write_text(out,encoding='utf-8')


def overview(registry,sources):
    tasks=registry['tasks']
    sizes=Counter(t['planned_scale_class'] for t in tasks)
    out='''# 60 个工程构建与测试 Agent 任务

版本：`sandbox_build_60_source_based_v1`  
用途：为 THENAME 补充不同规模的真实工程构建与测试轨迹。  
来源核查：2026-10-05。

## 一、这组任务怎么构造

本包选取 60 个具体工程，分六组，每组十题。默认任务是从源码完整构建声明的工程目标、运行有意义的官方测试，再向独立消费者交付可用的库、工具、运行时、服务程序或软件包。规模从 zlib 等基础库延伸到 PyTorch、TensorFlow、LLVM/Clang、Rust、Envoy 等大型工程。

完整构建是主场景，增量构建是同一任务的可选配置。每题都包含官方构建/测试入口、初始状态、交付要求、独立验收、规模配置、资源控制与后续使用方式。不会把改变 jobs、开关、cache 或重复运行当成额外任务数量。

这是一份来源已核查的任务设计与实现交接包：包含 60 张任务卡和 60 份提示模板，尚未在目标 sandbox 上完成工程构建与轨迹采集；实际资源测量字段保留为空。源码、依赖和巨型编译产物不随包分发。

## 二、六组覆盖

| 组 | 内容 | 数量 | 主要工程行为 |
|---|---|---:|---|
'''
    for group,(title,shape) in GROUPS.items():
        out+=f'| {group} | {title} | 10 | {shape} |\n'
    out+='''
这些分组用于组织来源生态，不是六个互斥资源 class。一个 PyTorch 或数据库构建可以同时表现出较高 CPU 工作量、链接阶段内存峰值、大量小文件操作和显著 build-tree 占用。正式分类仍依据固定参考配置上的实际画像。

## 三、为什么适合 cloud sandbox

工程构建把几类系统行为放在有实际交付目标的完整 session 内：configure 和代码生成会启动工具并探测环境；编译产生并行子进程和中间文件；链接与打包改变 CPU、内存和工作空间形态；测试运行新的程序、线程和临时服务；产物与构建状态可以跨 agent 调用保留。

因此，这组任务适合比较 native/container/VM 的实际执行成本，也适合在相同轨迹集合上改变 CPU 配额、内存限制、准入并发和状态保留策略。尤其是 process/metadata 覆盖，不能只看一个 syscall 总数：任务画像应区分进程创建/等待、文件路径检查、目录遍历、mmap/fault、同步和 socket 操作族。

工作空间与 I/O 分开记录。大量对象文件和安装包会增加状态保存规模，但不必然意味着持续 block-device I/O；下载依赖与镜像准备产生的流量也不能混作工具编译本身的访问量。

## 四、构建规模与 PyTorch

每题提供 core、reference、extended 三档。同一工程可通过真实组件、工具链阶段、设备编译后端和正式测试范围扩展工作量。参考档仍可为小工程：保留自然的小型工作负载，才便于判断 sandbox 在短任务和大任务上的差别。

PyTorch 是 `BUILDv1-F01`。其默认目标是 CPU 源码构建、wheel 交付、官方 CPU 测试，以及在源码目录之外的新环境安装该 wheel 后完成张量/模型功能验收。CUDA SDK 编译可作为扩展，但不把 GPU runtime 测试加入所有后端的默认门槛。这一任务测工程构建，与上一组使用 PyTorch 做 GPU 计算的任务不同。

'''
    out+='当前规划规模分布：'+ '、'.join(f'{SIZE_NAMES[k]} {sizes[k]} 题' for k in SIZE_NAMES)+'。这些是工程选型标签，正式运行时长、CPU、内存和磁盘额度由参考画像确定。\n\n'
    out+='''## 五、默认场景和验收

默认初始状态含固定源码、工具链与预置依赖，不含目标工程的构建输出或对象缓存。完整构建、工程测试与交付物消费都真实执行；仅 agent 决策 LLM 的响应和等待被轨迹回放替代。

验收包含三部分：核对产物来自本次源码构建；确认冻结的官方测试集合非空并实际执行；从源码树之外消费产物完成有意义的功能检查。例如，编译 C consumer 并链接新库，安装新 wheel 后调用 native 算子，用新构建的数据库执行带结果校验的查询。

增量场景从已验证的构建树出发，应用绑定的特性变化或真实补丁并重新验收。no-op rebuild 仅作为元数据/构建图诊断。依赖下载缓存、构建树、编译/action cache、页缓存和 sandbox snapshot 分别声明，以免缓存差异掩盖受测工作量。

## 六、60 题目录

'''
    for group,(title,_) in GROUPS.items():
        out += f'### {group} · {title}\n\n| ID | 工程任务 | 规划规模 |\n|---|---|---|\n'
        for t in tasks:
            if t['group']==group:
                out+=f'| {t["id"]} | {cell(t["title_zh"])} | {SIZE_NAMES[t["planned_scale_class"]]} |\n'
        out+='\n'
    out+='''## 七、文件怎么用

| 路径 | 用途 |
|---|---|
| `TASK_CATALOG.md` | 六组任务总览，链接到完整任务卡 |
| `task_briefs/` | 60 张任务卡，含具体构建/测试入口、规模与验收 |
| `agent_prompts/` | 60 份初始任务与可选后续请求模板 |
| `task_registry.json`、`tasks.jsonl` | 同一批完整机器可读任务记录 |
| `sources.json`、`SOURCES.md` | 官方页面/源码检查位置及版本信息 |
| `templates/` | source/dependency lock、实例、测试、回放和运行结果模板 |
| `BUILD_SCENARIOS.md` | clean、cache、incremental 和 no-op 的可比较场景 |
| `SOURCE_AND_DEPENDENCIES.md` | 版本、工具链、离线依赖和输入/产物边界 |
| `TEST_AND_ORACLE.md` | 测试集合、独立 consumer 和失败分类 |
| `MEASUREMENT.md` | 阶段、CPU/内存、workspace、I/O 与 OS 交互口径 |
| `REPLAY_AND_STATE.md` | 真实构建回放、后台作业和跨轮状态 |
| `BACKEND_CAPABILITIES.md` | Linux/CPU 默认范围与显式扩展能力 |
| `SIZE_AND_PILOTS.md` | 三档规模与推荐首批 12 题 |
| `DEDUP_AND_SCOPE.md` | 主工程计数、依赖血缘与已有任务的关系 |
| `CODEX_HANDOFF.md` | 从设计到可运行实例、轨迹及资源画像的实施步骤 |
| `scripts/` | 结构校验、视图重建和发布校验和脚本 |
| `VALIDATION_REPORT.json` | 本版结构与一致性校验结果 |
| `CHECKSUMS.sha256` | 发布包内文件的 SHA-256 |

在解压后的包根目录运行：

```bash
python3 scripts/validate_pack.py --self-check
```

修改 registry 后运行 `python3 scripts/render_views.py --root .`，再执行结构校验。实现新阶段后保存证据与 hash，更新 readiness；结构校验检查记录一致性，工程成功由任务专用 oracle 判定。

## 八、下一步怎么实施

建议每组先做两题，完成依赖预置、真实构建、独立验收、轨迹回放与统一资源记账：zlib/libgit2、CPython/binutils、FFmpeg/libvips、DuckDB/etcd、TypeScript/esbuild、NumPy/XGBoost。随后推进 PyTorch 等大型工程，而不是一次准备所有超大依赖环境。

这组任务侧重构建。数据库与服务程序会有本地功能消费者，但“sandbox 内部署服务—修改—从外部验收”的入口、长驻服务和跨轮管理问题仍适合下一组独立任务。
'''
    out+=f'\n本版共 {len(tasks)} 个主工程任务、{len(sources["sources"])} 条官方来源记录（{sources["metadata"]["unique_url_count"]} 个不同 URL）。完整来源与逐题绑定关系保存在包内。\n'
    return out


def templates(root):
    folder=root/'templates'
    folder.mkdir(exist_ok=True)
    write_json(folder/'source_dependency_lock.template.json',{
        'schema_version':'build-source-lock-v1','status':'template','task_id':None,'instance_id':None,
        'primary_source':{'source_id':None,'url':None,'revision':None,'tree_sha256':None,'local_path':None},
        'submodules':[],'patches':[],'dependency_assets':[],
        'toolchains':{'compiler':None,'linker':None,'bootstrap_runtime':None,'build_tools':[]},
        'environment':{'image_digest':None,'os':None,'architecture':None,'package_manifest_sha256':None},
        'source_license':None,'offline_preflight_evidence':None,
        'target_artifacts_preexisting':False,'dependency_cache_manifest_sha256':None,
    })
    write_json(folder/'instance.template.json',{
        'schema_version':'build-instance-v1','status':'template','task_id':None,'instance_id':None,
        'canonical_goal_key':None,'source_dependency_lock_sha256':None,'scale_profile':'reference',
        'scenario':'clean-source-build','initial_prompt_path':None,'continuation_prompt_path':None,
        'paths':{'source_root':None,'build_root':None,'install_root':None,'artifact_root':None},
        'targets':[],'required_features':[],'resolved_build_commands':[],
        'parallelism':{'build_jobs':None,'test_jobs':None,'linker_threads':None,'runtime_threads':None},
        'cache_state':{'dependency_cache':None,'build_tree':None,'compiler_action_cache':None,'page_cache_policy':None,'sandbox_snapshot':None},
        'test_selection':{'manifest_path':None,'sha256':None,'count_unit':None,'expected_nonempty':True,'declared_skips':[]},
        'consumer_verifier':{'implementation_sha256':None,'input_manifest_sha256':None,'required_output_rules':[]},
        'incremental_delta':{'enabled':False,'base_state_sha256':None,'patch_or_config_delta_sha256':None,'acceptance_sha256':None},
        'sandbox_budget':{'vcpu':None,'memory_gib':None,'workspace_gib':None,'pids_limit':None},
        'execution_limits':{'timeout_s':None,'cancel_grace_s':None,'drain_cutoff_s':None},
    })
    write_json(folder/'test_evidence.template.json',{
        'schema_version':'build-tests-v1','status':'template','task_id':None,'instance_id':None,
        'harness':None,'harness_version':None,'selection_manifest_sha256':None,
        'discovery_command':None,'execution_command':None,'count_unit':None,
        'counts':{k:None for k in ['discovered','selected','executed','passed','failed','skipped','expected_failures','timeouts']},
        'required_cases':[],'declared_skips':[],'unexpected_skips':[],
        'exit_code':None,'raw_report':{'path':None,'sha256':None},'process_evidence':{'path':None,'sha256':None},
        'nonempty_check':None,'selection_match':None,'oracle_verdict':None,
    })
    write_json(folder/'replay_manifest.template.json',{
        'schema_version':'build-replay-v1','status':'template','corpus_version':None,
        'task_id':None,'instance_id':None,'instance_sha256':None,'trace_id':None,'trace_sha256':None,
        'planned_arrival_offset_s':None,'model_wait_scale':1.0,'preserve_dependencies':True,
        'tool_execution':'real','initial_state_sha256':None,'cache_state_sha256':None,
        'recorded_model_turns':[],'commands':[],'dependency_edges':[],
        'runtime_bindings':{'process_ids':[],'job_handles':[],'service_ports':[],'temporary_paths':[]},
        'lifecycle_policy':None,'source_config_test_manifest_sha256':None,
        'completion_contract':{'background_jobs_joined':True,'test_evidence_required':True,'artifact_validation_required':True},
    })
    write_json(folder/'run_result.template.json',{
        'schema_version':'build-result-v1','status':'template','run_id':None,'task_id':None,'instance_id':None,
        'manifest_sha256':None,'backend':None,'host_configuration':None,
        'timing':{k:None for k in ['planned_arrival','admitted','sandbox_ready','tool_start','task_complete','sandbox_released']},
        'phase_events_path':None,'counter_samples_path':None,
        'outcome':{'build_integrity':None,'official_tests':None,'consumer_verification':None,'failure_class':None,'unsupported_reason':None,'incomplete':None},
        'measurements':{k:None for k in MEASUREMENTS},
        'counter_scope':{'host_or_guest':None,'memory_definition':None,'attribution':None,'sample_period_s':None,'missing_reasons':{}},
        'test_evidence_sha256':None,'artifacts':[],
        'grader_overhead':{'wall_s':None,'cpu_core_s':None,'memory_gib_s':None},
    })
    write_json(folder/'backend_capabilities.template.json',{
        'schema_version':'build-backend-capabilities-v1','status':'template','backend':None,'version':None,
        'architecture':None,'kernel_or_abi':None,
        'capabilities':{k:None for k in ['processes','threads','signals','file_locks','symlinks','mmap','loopback_tcp','unix_sockets','shared_memory','cpu_isa','software_rendering','gpu_sdk','gpu_runtime']},
        'evidence':{},'unsupported_profiles':[],
    })
    (folder/'README.md').write_text('''# 实例模板

这些 JSON 是字段模板，null 由真实实例与证据填充，不是可直接执行的默认配置。task registry 绑定工程来源；instance 进一步冻结源码、工具链、目标、测试、缓存和并行配置。

- source_dependency_lock：代码、依赖、bootstrap 工具链和镜像身份。
- instance：clean/incremental 场景、具体构建目标、测试集合和资源预算。
- test_evidence：harness 的测试单位、非空集合、实际执行与失败/skip。
- replay_manifest：完整轨迹、计划到达、当前动态句柄和真实工具依赖。
- run_result：阶段、资源、结果、失败和产物。
- backend_capabilities：逐项证实的平台能力；null 表示未验证。

resource 标签按 profiling 确定；成功产物的 hash 证明本次身份，不自动要求不同编译环境产生逐字节相同文件。后台作业的结束依据当前执行结果，不能由记录的 sleep 推断。
''',encoding='utf-8')


def build(group_dir,root):
    root.mkdir(parents=True,exist_ok=True)
    tasks=[]; all_sources=[]; notes={}
    for group in GROUPS:
        d=json.loads((group_dir/f'group_{group}.json').read_text(encoding='utf-8'))
        notes[group]=d.get('notes',[])
        for s in d['sources']:
            s=dict(s); s.pop('citation_ref',None)
            all_sources.append(s)
        for raw in d['tasks']:
            t=dict(raw); t['group']=group
            t['readiness']={'stage':'source_grounded_design','evidence':{k:None for k in EVIDENCE_KEYS}}
            t['reference_measurements']={k:None for k in MEASUREMENTS}
            t['resource_tags_status']='expected_unmeasured'
            t['default_scenario']='clean-source-build'
            t['task_brief_path']=f'task_briefs/{t["id"]}.md'
            t['agent_prompt_path']=f'agent_prompts/{t["id"]}.md'
            tasks.append(t)
    common_sources_path=group_dir/'common_sources.json'
    if common_sources_path.exists():
        all_sources.extend(json.loads(common_sources_path.read_text(encoding='utf-8')))
    tasks.sort(key=lambda x:x['id']); all_sources.sort(key=lambda x:x['id'])
    registry={'metadata':{
        'schema_version':'build-task-design-v1','package_version':'sandbox_build_60_source_based_v1',
        'created_on':'2026-10-05','task_count':len(tasks),'counting_unit':'primary_engineering_project',
        'stage_at_release':'source_grounded_design','default_scenario':'clean-source-build',
        'resource_values_scope':'planned size labels; actual reference measurements are null until profiled',
        'group_notes':notes,
    },'tasks':tasks}
    sources={'metadata':{'inspected_on':'2026-10-05','source_record_count':len(all_sources),'unique_url_count':len({s['url'] for s in all_sources})},'sources':all_sources}
    write_json(root/'task_registry.json',registry); write_json(root/'sources.json',sources)
    for p in (group_dir/'common_docs').glob('*.md'):
        shutil.copy2(p,root/p.name)
    (root/'scripts').mkdir(exist_ok=True)
    shutil.copy2(Path(__file__),root/'scripts/render_views.py')
    shutil.copy2(group_dir/'validate_pack.py',root/'scripts/validate_pack.py')
    shutil.copy2(group_dir/'update_checksums.py',root/'scripts/update_checksums.py')
    render_views(root,registry,sources)
    (root/'README.md').write_text(overview(registry,sources),encoding='utf-8')
    templates(root)
    return registry,sources


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--from-groups',type=Path)
    args=p.parse_args(); root=args.root.resolve()
    if args.from_groups:
        registry,sources=build(args.from_groups.resolve(),root)
    else:
        registry=json.loads((root/'task_registry.json').read_text(encoding='utf-8'))
        sources=json.loads((root/'sources.json').read_text(encoding='utf-8'))
        render_views(root,registry,sources)
    print(json.dumps({'tasks':len(registry['tasks']),'sources':len(sources['sources']),'root':str(root)},ensure_ascii=False))


if __name__=='__main__':
    main()
