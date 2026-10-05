"""Export reviewable deliveries, measured evidence and separate frozen debug inputs."""
import ast,csv,hashlib,json,os,re,shutil,time,zipfile,sys
from pathlib import Path
from container import ROOT,POLICY

OUT=ROOT/'release';OUT.mkdir(exist_ok=True);PACKAGE=OUT/'gpu60_review_v1'
if PACKAGE.exists():shutil.rmtree(PACKAGE)
PACKAGE.mkdir()
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(8<<20),b''):h.update(part)
    return h.hexdigest()
def copy(src,target):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
def exported(obj):
    if isinstance(obj,str):return (obj[len('gpu_suite/'):] if obj.startswith('gpu_suite/') else obj).replace(str(ROOT),'$SUITE_ROOT').replace('/home/zrji/.venv','$BASE_PYTHON_ENV')
    if isinstance(obj,list):return [exported(v) for v in obj]
    if isinstance(obj,dict):return {k:exported(v) for k,v in obj.items()}
    return obj
def write(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def telemetry(run):
    probes=[]
    for p in run.glob('*/resources.jsonl'):
        if p.parent.name in ['compile_isolation','evaluation_isolation']:continue
        samples=[]
        for line in p.read_text().splitlines():
            try:s=json.loads(line);v=s['gpu'].split(',');stats=json.loads(s.get('container_stats') or '{}');samples.append((float(s['t']),int(v[1].strip()),int(v[2].strip()),int(v[3].strip()),stats.get('MemUsage'),stats.get('CPUPerc')))
            except Exception:continue
        if samples:probes.append({'phase':p.parent.name,'samples':len(samples),'sampled_elapsed_s':samples[-1][0],'gpu_total_peak_mib':max(v[1] for v in samples),'gpu_utilization_mean_pct':sum(v[2] for v in samples)/len(samples),'gpu_temperature_peak_c':max(v[3] for v in samples),'container_memory_samples':[v[4] for v in samples if v[4]]})
    return probes
progress=json.loads((ROOT/'progress.json').read_text());records=[];usage={};models=set()
for task in sorted((ROOT/'tasks').iterdir()):
    latest=json.loads((task/'latest_run.json').read_text());run=Path(latest['run_directory']);run=run if run.is_absolute() else ROOT/run
    solution=run/'workspace/solution';assert (solution/'main.py').exists();ast.parse((solution/'main.py').read_text())
    record=next(x for x in progress['tasks'] if x['id']==task.name);manifest=json.loads((task/'input/manifest.json').read_text());evaluation=latest.get('evaluation',{});gated=not bool(record.get('debug_ready'))
    target=PACKAGE/'tasks'/task.name
    for name in ['TASK.md','source_spec.json','original_prompt.md','instance_plan.json','implementation_contract.json']:
        if (task/name).exists():copy(task/name,target/name)
    shutil.copytree(solution,target/'solution',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    copy(task/'input/manifest.json',target/'input/manifest.json')
    primary_hash=sha(solution/'main.py');snapshot=exported(latest);snapshot['run_directory']='tasks/'+task.name+'/runs/delivered';write(target/'latest_run.json',snapshot)
    delivery=exported(json.loads((run/'author_delivery.json').read_text())) if (run/'author_delivery.json').exists() else None
    if not delivery and latest.get('code_source_run'):
        p=Path(latest['code_source_run'])/'author_delivery.json'
        if p.exists():delivery=exported(json.loads(p.read_text()))
    if delivery:write(target/'delivery.json',{'run_command':delivery['run_command'],'notes':delivery.get('notes')})
    write(target/'evidence/latest_execution.json',snapshot);write(target/'evidence/evaluation.json',evaluation)
    if (run/'evaluation_command.json').exists():write(target/'evidence/evaluation_command.json',exported(json.loads((run/'evaluation_command.json').read_text())))
    probes=telemetry(run);write(target/'evidence/resource_profile.json',probes)
    for phase in run.iterdir():
        if not phase.is_dir() or not (phase/'resources.jsonl').exists():continue
        for f in ['resources.jsonl','admission.jsonl','final_state.json']:
            if (phase/f).exists():copy(phase/f,target/'evidence'/phase.name/f)
    # The export contains input locks and readers; labels are in the separate
    # debug-input archive and are never mounted in the solver container.
    inputs=[]
    for p in sorted((task/'input').rglob('*')):
        if p.is_file() and not p.is_symlink():inputs.append({'name':str(p.relative_to(task/'input')),'bytes':p.stat().st_size,'sha256':sha(p)})
    write(target/'input_lock.json',{'task_id':task.name,'assets_ready':not gated,'files':inputs})
    missing=manifest.get('required_files',[]);modules=manifest.get('required_modules',[])
    details={'id':task.name,'title':record['title'],'code_authored':True,'code_model':'deepseek-flash','main_py_sha256':primary_hash,'source_files':{str(p.relative_to(solution)):sha(p) for p in solution.rglob('*') if p.is_file() and '__pycache__' not in p.parts},'container_compile_passed':bool(record.get('container_compile_passed')),'debug_ready':not gated,'execution_exit_code':latest.get('trial_result',{}).get('exit_code'),'debug_protocol_passed':bool(record.get('container_tested')),'reference_large_tested':False,'formal_quality_passed':None,'evaluation':evaluation,'model_or_algorithm':json.loads((task/'instance_plan.json').read_text())['model_or_algorithm'],'deviations':manifest.get('deviations',[]),'missing_native_files':missing,'missing_native_modules':modules,'resource_profile':probes,'solver_final_event_received':bool(latest.get('solver_declared_complete'))}
    write(target/'evidence/provenance.json',details);records.append(details)
    for p in list(task.glob('author_attempts/*.json'))+list(task.glob('runs/*/*response*.json'))+list(task.glob('runs/*/directed_repair*.json')):
        try:
            raw=json.loads(p.read_text());identifier=raw.get('id')
            if identifier and raw.get('usage'):usage.setdefault(identifier,{'model':raw.get('model'),'usage':raw['usage']})
        except Exception:pass
for p in ROOT.glob('*.py'):copy(p,PACKAGE/p.name)
for p in (ROOT/'runtime').rglob('*'):
    if p.is_file() and '__pycache__' not in p.parts:copy(p,PACKAGE/'runtime'/p.relative_to(ROOT/'runtime'))
shutil.copytree(ROOT/'source_design',PACKAGE/'source_design')
for p in (ROOT/'assets/models').glob('*/asset_lock.json'):copy(p,PACKAGE/'model_locks'/p.parent.name/p.name)
for p in (ROOT/'assets/models/torchvision').glob('*.json'):copy(p,PACKAGE/'model_locks/torchvision'/p.name)
for p in (ROOT/'source_audit').glob('*'):
    if p.is_file():copy(p,PACKAGE/'source_audit'/p.name)
for name in ['checks.json','container.json','final_state.json','resources.jsonl']:
    p=ROOT/'runs/runtime_smoke'/name
    if p.exists():copy(p,PACKAGE/'runtime/smoke_evidence'/name)
copy(ROOT/'runs/final_compile/evaluation/compilation.json',PACKAGE/'runtime/compilation.json')
counts={'tasks':60,'flash_implementations':60,'container_compile_and_cli_passed':sum(r['container_compile_passed'] for r in records),'debug_assets_ready':sum(r['debug_ready'] for r in records),'debug_protocol_passed':sum(r['debug_protocol_passed'] for r in records),'native_assets_pending':sum(not r['debug_ready'] for r in records),'reference_large_tested':0}
write(PACKAGE/'status.json',{'counts':counts,'tasks':records,'reference_large_tested':False,'generated_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
portable_progress=exported(progress)
for item in portable_progress['tasks']:
    if item.get('container_tested'):item['evaluation_path']='tasks/'+item['id']+'/evidence/evaluation.json'
write(PACKAGE/'progress.json',portable_progress)
write(PACKAGE/'flash_usage.json',{'unique_recorded_responses':len(usage),'prompt_tokens':sum(r['usage'].get('prompt_tokens',0) for r in usage.values()),'completion_tokens':sum(r['usage'].get('completion_tokens',0) for r in usage.values()),'total_tokens':sum(r['usage'].get('total_tokens',0) for r in usage.values()),'note':'Deduplicated provider response IDs include failed/truncated/repaired calls. No credential, price estimate, prompts or reasoning trace in this file.'})
lines=['# GPU60 实施与验收记录','',f"60 个任务都已形成规格与 Flash 实现；容器编译/CLI检查通过 {counts['container_compile_and_cli_passed']}/60。{counts['debug_protocol_passed']}/48 个已准备真实输入的调试实例通过独立验收。12 个原生任务仍缺数据、权重或专用环境；正式 reference-large 执行数为 0。",'',
'验收通过指本次冻结 debug 变体的执行与交付协议通过。模型质量另报，调试规模、替代模型或替代数据不能冒充原任务正式配置。原始60题、119条来源完整保存在 source_design/。', '',
'## 容器与资源保护','',
'实际后端为 Docker + NVIDIA，GPU 单任务串行，单容器 6 CPU、24 GiB RAM、无 swap、256 PID、8 GiB 工作 tmpfs、1 GiB 临时 tmpfs、单文件 2 GiB、命令 300 秒。断网、只读根文件系统、drop ALL capabilities、no-new-privileges；只挂载当前输入、模型和必要产物，未挂载 Docker socket、宿主 home 或 API key。', '',
'GPU 准入检查空闲显存/利用率，PyTorch allocator 上限75%，设备总显存超过28GiB、过热、宿主可用内存低于12GiB或工作盘可用空间低于50GiB时终止自己的容器。Docker没有内核级显存配额；非PyTorch分配由监控兜底。容器共享宿主内核与GPU驱动，尚未进行microVM或多租户安全验证。', '',
'D07评分器曾因捕获512-token完整trace触发容器OOM，Docker记录OOMKilled=true，宿主可用内存保持90GiB以上。评分器现捕获一次完整prefill前向，全部token仍独立重算。早期任务的OOM、超时、显存保护终止及模型错误不计作通过。', '',
'## 已发现的质量边界','',
'A07小推荐模型的独立验证AUC为0.39；B10深度预测误差很大；F10滚动预测RMSE高于持久性基线；D04的SQL执行正确率为2/6，D03隐藏HumanEval测试通过6/8。这些是任务侧小模型的实际结果。debug协议验收不会把这些低质量结果改写成正式任务通过。生成媒体的语义质量、声纹相似度、文档版面和长视频理解仍需补完整内容评分。', '',
'## 状态表','',
'| ID | 任务 | 实际模型/算法 | 容器调试状态 | 正式大规模 |','|---|---|---|---|---|']
for r in records:
    state='debug协议通过' if r['debug_protocol_passed'] else '原生资产/环境待补' if not r['debug_ready'] else '调试未通过'
    lines.append('| '+r['id']+' | '+r['title']+' | '+str(r['model_or_algorithm']).replace('|','/')+' | '+state+' | 未执行 |')
lines+=['','## 待补的12个原生任务','',
'这些任务的完整上游适配器通过源码编译和CLI检查，doctor在缺失资产时返回78。没有真实GPU执行或独立运行正确性证据，其原生评价器也尚未实现/验收。', '']
for r in records:
    if not r['debug_ready']:lines.append('- '+r['id']+'：'+r['title']+'。文件：`'+'`, `'.join(r['missing_native_files'])+'`；模块：`'+'`, `'.join(r['missing_native_modules'])+'`。')
lines+=['','## 回放与评分范围','',
'所有任务侧训练、模型推理、媒体生成、索引和模拟均实际执行。Flash调用在宿主控制器完成，key仅通过stdin读入内存，未写入文件或传入容器。求解器状态、程序退出、debug协议评分、模型质量和正式规模结果分别记录。F10等早期运行的LLM结束事件缺失与可验证产物通过可同时存在；不能把两者混为一个成功标记。', '',
'当前评分器用于合作型agent的调试验收：原始求解阶段看不到隐藏标签，交付目录在评分阶段只读；独立标准模型/CPU公式核对原始完整产物，再重放代码或新请求。评分器和重放代码仍在同一评估容器内，尚未完成针对恶意程序的oracle隔离、评分进程权限隔离与抗篡改验证。', '',
'资源文件是单次调试的设备总NVML采样和容器统计，采样间隔受docker stats耗时影响；不是每进程显存计账，短任务峰值可能漏采，也不代表冷启动、多GPU、云准入/抢占/迁移实验。', '',
'## 交付与复现','',
'review ZIP含60题、60份Flash源码、原始规格/提示、模型和输入锁、48题评价器、容器控制器、来源准备脚本与测得证据；不含模型权重、训练checkpoint、完整媒体、完整思维链或API key。独立的debug_inputs ZIP含冻结真实输入与隐藏oracle；将其解压到review目录。原机的全部模型与执行产物仍保留在 gpu_suite/ 下。', '',
'模型权重按 model_locks/ 中的revision和SHA256恢复；restore_models.py负责HF模型，TorchVision/ProPainter及其他来源按各锁的URL补齐。原始prepare脚本中部分数据接口依赖上游当前数据视图，重新运行可能产生新实例；优先使用本次冻结输入包，内容不符时拒绝当作同一实例。', '',
'此实现采用挂载Python环境的容器方案，已在本机RTX5090/driver570.124.06验证；跨机器完整冷启动重建尚未验收。默认Transformers5.12，C09/C10用4.57.3兼容官方上游。Torch2.11cu128与CUDA12.8NVRTC通过独立挂载提供；宿主原环境与驱动未更换。现有cuDNN运行库9.17与Torch编译9.19存在RNN版本检查差异，C07明确关闭cuDNN调度并用真实CUDA kernel执行，不能将该兼容方式推广为所有上游环境可用。', '',
'```bash','cd gpu60_review_v1','export SBENCH_PYTHON_ENV=/path/to/your/python3.12/venv','docker build -t sbench-gpu-runtime:v1 runtime','python restore_models.py --only Qwen/Qwen2.5-0.5B-Instruct','python run_delivery.py GPUv1-E05 --command "python solution/main.py build --input input --output output"','python grade_task.py GPUv1-E05','```', '',
'完整环境的包版本/元数据路径见 runtime/environment_*.json；需要依照版本提供独立的Python环境与pydeps/cuda128deps/compat_deps/qwen_tts_deps/cuda_compat。上述命令假设相应环境、冻结输入与任务模型已恢复，源码包本身不包含这些大体积依赖。']
(PACKAGE/'REPORT.md').write_text('\n'.join(lines)+'\n')
readme=f'''# GPU60 review v1

60份任务规格与DeepSeek Flash源码，{counts['debug_protocol_passed']}个debug实例独立验收，12个原生任务待补资产，正式大规模未执行。

从REPORT.md开始；status.json给出每题准确状态与质量/资源记录。TASK.md是本轮求解契约，source_spec.json是原始正式规格，input/manifest.json冻结实际调试变体。三者不可互相冒充。

模型与大体积环境不在ZIP中。debug_inputs ZIP单独提供真实输入和私有oracle，解压到此目录后按REPORT.md恢复环境和模型。原机gpu_suite/assets/models与tasks/*/runs保存完整资产及结果。

运行使用run_delivery.py，它为每题建立有界容器；验收用grade_task.py。缺资产原生任务doctor返回78，不会生成伪结果。参考本机已验收的环境版本，跨主机冷启动仍需验证。
'''
(PACKAGE/'README.md').write_text(readme)
profiles=[{'id':r['id'],'profiles':r['resource_profile'],'note':'Device-total samples; coarse single-debug-run characterization, not per-process GPU accounting.'} for r in records]
(PACKAGE/'resource_profiles.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in profiles))
# Auxiliary public source audit links are deliberately separate from the original119.
(PACKAGE/'SOURCES_SUPPLEMENT.md').write_text('''# Additional implementation checks

- LAMMPS Ta SNAP files and pair_coeff semantics: https://docs.lammps.org/pair_snap.html ; source commit e891a3e10973c1a729e391a0aefaa02fd70f8c0f.
- EquiformerV2 original ocpmodels entry point: https://github.com/atomicarchitects/equiformer_v2/blob/d5ad4be729b56f74012ebb7f097f77c5b00a1004/main_oc20.py .
- OpenFold inference entry point: https://github.com/aqlaboratory/openfold/blob/be2ec1841f16c966c65ae0e7599ebbadc725757d/run_pretrained_openfold.py .

These checks do not assert those gated tasks were executed.
''')
checks=[]
for p in PACKAGE.rglob('*'):
    if p.is_file():
        if p.suffix in ['.py','.json','.jsonl','.md','.txt','.sh'] and re.search(rb'sk-[0-9a-fA-F]{32}',p.read_bytes()):raise RuntimeError('Credential-like text in export '+str(p))
        checks.append(sha(p)+'  '+str(p.relative_to(PACKAGE)))
(PACKAGE/'SHA256SUMS').write_text('\n'.join(sorted(checks))+'\n')
review=OUT/'gpu60_review_v1.zip'
with zipfile.ZipFile(review,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in PACKAGE.rglob('*'):
        if p.is_file():z.write(p,str(p.relative_to(OUT)))
inputs_zip=OUT/'gpu60_debug_inputs_v1.zip'
if '--review-only' not in sys.argv or not inputs_zip.exists():
    with zipfile.ZipFile(inputs_zip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for t in sorted((ROOT/'tasks').iterdir()):
            for base in ['input','oracle']:
                for p in (t/base).rglob('*'):
                    if p.is_file():z.write(p,str(Path('tasks')/t.name/base/p.relative_to(t/base)))
        # E05 validation requires the independently frozen full SIFT1M neighbors.
        z.write(ROOT.parent/'pilot_gpu/oracle/neighbors.npy','benchmark_oracles/sift1m_neighbors.npy')
write(OUT/'release_manifest.json',{'counts':counts,'review_zip':{'bytes':review.stat().st_size,'sha256':sha(review)},'debug_inputs_zip':{'bytes':inputs_zip.stat().st_size,'sha256':sha(inputs_zip)}})
copy(PACKAGE/'REPORT.md',ROOT/'REPORT.md');copy(PACKAGE/'README.md',ROOT/'README.md')
print(json.dumps({'counts':counts,'review_mb':review.stat().st_size/2**20,'debug_inputs_mb':inputs_zip.stat().st_size/2**20},indent=2))
