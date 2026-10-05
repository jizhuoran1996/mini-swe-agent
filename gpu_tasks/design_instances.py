"""Render all 60 operational task prompts; readiness remains evidence based."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
registry=json.loads((ROOT/'source_design/task_registry.json').read_text())
small_models={
 'A01':'HuggingFaceTB/SmolLM2-135M-Instruct', 'A02':'HuggingFaceTB/SmolLM2-135M-Instruct',
 'A03':'Helsinki-NLP/opus-mt-en-de', 'A04':'openai/whisper-tiny', 'A05':'openai/whisper-tiny',
 'A06':'facebook/wav2vec2-base', 'A07':'DLRM with actual source subset category domains',
 'A08':'Qwen/Qwen2.5-0.5B-Instruct + LoRA', 'A09':'prajjwal1/bert-tiny dual encoders', 'A10':'prajjwal1/bert-tiny masked language pretraining',
 'B01':'TorchVision ResNet-50', 'B02':'TorchVision RetinaNet ResNet50-FPN (COCO category variant)',
 'B03':'TorchVision Mask R-CNN ResNet50-FPN', 'B04':'SegFormer B0 or source-native MiT-B2',
 'B05':'source-native 3D U-Net', 'B06':'source-native CenterPoint, single-scene debug',
 'B07':'source-native Cylinder3D or explicitly labeled PointNet debug adapter',
 'B08':'VideoMAE ViT-Base','B09':'OSTrack ViT-Base','B10':'Depth Anything V2 metric depth small encoder',
 'C01':'stabilityai/stable-diffusion-xl-base-1.0','C02':'public Stable Diffusion inpainting debug variant (requires explicit asset lock)',
 'C03':'public SD ControlNet Canny debug variant (requires explicit asset lock)',
 'C04':'Wan-AI/Wan2.1-T2V-1.3B','C05':'Wan-AI/Wan2.2-TI2V-5B','C06':'ProPainter official checkpoints',
 'C07':'facebook/musicgen-melody','C08':'stabilityai/stable-audio-open-1.0','C09':'Qwen/Qwen3-TTS-12Hz-1.7B-Base','C10':'TripoSR debug shape pipeline with declared material extraction',
 'D01':'Qwen/Qwen2.5-0.5B-Instruct','D02':'Qwen/Qwen2.5-0.5B-Instruct','D03':'Qwen/Qwen2.5-Coder-0.5B-Instruct','D04':'Qwen/Qwen2.5-Coder-0.5B-Instruct',
 'D05':'Qwen/Qwen2.5-VL-3B-Instruct','D06':'Qwen/Qwen2.5-VL-3B-Instruct','D07':'Qwen/Qwen2.5-VL-3B-Instruct',
 'D08':'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','D09':'cross-encoder/ms-marco-MiniLM-L6-v2','D10':'Qwen/Qwen2.5-0.5B-Instruct',
 'E01':'source-native relational GPU processing','E02':'source-native GPU feature ETL','E03':'XGBoost CUDA hist',
 'E04':'XGBoost CUDA regression','E05':'native SIFT1M retrieval debug variant (not a SIFT1B prefix)',
 'E06':'GPU K-means on real source descriptors','E07':'GPU PageRank on a frozen genuine graph subset','E08':'GPU community detection on a frozen genuine graph subset',
 'E09':'small heterogeneous GNN on real source graph/features','E10':'small GraphSAGE on real citation graph/features',
 'F01':'source-native smaller CosmoFlow training budget','F02':'source-native smaller DeepCAM training budget',
 'F03':'ESMFold single-chain debug alternative without the OpenFold database requirement',
 'F04':'source-native smaller catalyst checkpoint / exact declared relaxation recipe',
 'F05':'native GROMACS short run; smaller genuinely sourced structure only as a distinct declared debug variant',
 'F06':'source-native LAMMPS SNAP Ta nrep=4 short GPU run',
 'F07':'source-native FCN3 two-member, two-step forecast','F08':'source-native CorrDiff five-sample inference',
 'F09':'source-native AeroGraphNet reduced genuine vehicle list','F10':'source-native FNO reduced time window on genuine The Well fields'
}

for t in registry['tasks']:
    tid=t['id'];short=tid.split('-')[1];folder=ROOT/'tasks'/tid
    debug={'id':tid,'scale':'debug_only','model_or_algorithm':small_models[short],
           'source_debug_plan':t['scale_plan']['debug'],'reference_large':t['scale_plan']['reference_large'],
           'binding_status':'must_freeze_exact_models_and_inputs_before_execution',
           'formal_large_tested':False,'resource_policy':'runtime/policy.json',
           'notes':['Model substitutions are explicitly debug-only. Data may not be fabricated or duplicated to impersonate the source.','An unavailable source remains unavailable unless the designer freezes a named genuine replacement and records the lineage change.','This file does not assert that assets, code or GPU execution have passed.']}
    if not (folder/'instance_plan.json').exists():(folder/'instance_plan.json').write_text(json.dumps(debug,ensure_ascii=False,indent=2)+'\n')
    if (folder/'TASK.md').exists():continue
    text='# '+tid+'：'+t['title_zh']+'\n\n'+t['agent_goal']+'\n\n'
    text+='本次执行是小规模真实 GPU 调试实例。原包正式配置完整保留；调试通过不能写成正式规模通过。模型或算法计划：`'+small_models[short]+'`。实际输入、模型 revision、路径和 SHA256 必须以只读 `input/manifest.json` 为准；资产未准备好时，报告缺失，不生成假输入或假预测。\n\n'
    text+='## 来源及范围\n\n'+t['source_task_or_workload']+'\n\n调试范围：'+json.dumps(t['scale_plan']['debug'],ensure_ascii=False)+'\n\n'
    text+='## 实际工作\n\n'+''.join('- '+x+'\n' for x in t['required_work'])+'\n'
    text+='## 交付物\n\n'+''.join('- '+x+'\n' for x in t['deliverables'])+'\n'
    text+='统一提供 `solution/main.py`、`solution/README.md`、可恢复产物和 `output/run.json`。源码和输出只能写到 `solution/`、`output/`。说明所有入口、依赖、输入覆盖、精度、seed、参数、完成事件、阶段耗时和实际设备；训练任务必须记录参数更新与恢复状态，服务任务必须记录真正可查询的 ready。\n\n'
    text+='## 后续使用和独立验收\n\n'+t['continuation']+'\n\n'+''.join('- '+x+'\n' for x in t['oracle'])+'\n'
    text+='禁止情况：\n\n'+''.join('- '+x+'\n' for x in t['negative_cases'])+'\n'
    text+='## 测试环境\n\n工作目录 `/workspace`，单张 RTX 5090，容器根文件系统和输入只读，无网络，不挂载主机 home、Docker socket 或 API key。最多 24 GiB 主机 RAM、无 swap、6 CPU、256 进程、8 GiB 工作区。实际参数见运行 manifest；GPU 作业串行，并保留显存余量。超限会终止本容器。使用已经提供的 `python` 和框架；缺失资产应报告，不能在主机执行替代工作。\n\n请在容器中实际实现和执行任务，再交付源码、可重载产物和完成说明。不要人为增加工具调用、重复样本、sleep 或无用 GPU 状态。\n'
    (folder/'TASK.md').write_text(text)
print('60 operational prompts and instance plans rendered; asset/execution readiness remains separate.')
