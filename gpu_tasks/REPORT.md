# GPU60 实施与验收记录

60 个任务都已形成规格与 Flash 实现；容器编译/CLI检查通过 60/60。48/48 个已准备真实输入的调试实例通过独立验收。12 个原生任务仍缺数据、权重或专用环境；正式 reference-large 执行数为 0。

验收通过指本次冻结 debug 变体的执行与交付协议通过。模型质量另报，调试规模、替代模型或替代数据不能冒充原任务正式配置。原始60题、119条来源完整保存在 source_design/。

## 容器与资源保护

实际后端为 Docker + NVIDIA，GPU 单任务串行，单容器 6 CPU、24 GiB RAM、无 swap、256 PID、8 GiB 工作 tmpfs、1 GiB 临时 tmpfs、单文件 2 GiB、命令 300 秒。断网、只读根文件系统、drop ALL capabilities、no-new-privileges；只挂载当前输入、模型和必要产物，未挂载 Docker socket、宿主 home 或 API key。

GPU 准入检查空闲显存/利用率，PyTorch allocator 上限75%，设备总显存超过28GiB、过热、宿主可用内存低于12GiB或工作盘可用空间低于50GiB时终止自己的容器。Docker没有内核级显存配额；非PyTorch分配由监控兜底。容器共享宿主内核与GPU驱动，尚未进行microVM或多租户安全验证。

D07评分器曾因捕获512-token完整trace触发容器OOM，Docker记录OOMKilled=true，宿主可用内存保持90GiB以上。评分器现捕获一次完整prefill前向，全部token仍独立重算。早期任务的OOM、超时、显存保护终止及模型错误不计作通过。

## 已发现的质量边界

A07小推荐模型的独立验证AUC为0.39；B10深度预测误差很大；F10滚动预测RMSE高于持久性基线；D04的SQL执行正确率为2/6，D03隐藏HumanEval测试通过6/8。这些是任务侧小模型的实际结果。debug协议验收不会把这些低质量结果改写成正式任务通过。生成媒体的语义质量、声纹相似度、文档版面和长视频理解仍需补完整内容评分。

## 状态表

| ID | 任务 | 实际模型/算法 | 容器调试状态 | 正式大规模 |
|---|---|---|---|---|
| GPUv1-A01 | 训练可交付的多轮指令对话模型 | HuggingFaceTB/SmolLM2-135M-Instruct | debug协议通过 | 未执行 |
| GPUv1-A02 | 训练并验证偏好对齐后的对话模型 | HuggingFaceTB/SmolLM2-135M-Instruct | debug协议通过 | 未执行 |
| GPUv1-A03 | 构建可离线交付的英德机器翻译模型 | Helsinki-NLP/opus-mt-en-de | debug协议通过 | 未执行 |
| GPUv1-A04 | 适配大规模语音转写模型并交付转录结果 | openai/whisper-tiny | debug协议通过 | 未执行 |
| GPUv1-A05 | 训练英语语音到德语文本的翻译模型 | fairseq source s2t_transformer_s CoVoST2 en-de recipe | 原生资产/环境待补 | 未执行 |
| GPUv1-A06 | 用大规模无标注音频扩展语音表示模型 | facebook/wav2vec2-base | debug协议通过 | 未执行 |
| GPUv1-A07 | 训练并交付大表嵌入的点击率模型 | DLRM with actual source subset category domains | debug协议通过 | 未执行 |
| GPUv1-A08 | 适配70B长报告摘要模型并交付可复用适配器 | Qwen/Qwen2.5-0.5B-Instruct | debug协议通过 | 未执行 |
| GPUv1-A09 | 训练问答检索双编码器并交付检索表征 | prajjwal1/bert-tiny | debug协议通过 | 未执行 |
| GPUv1-A10 | 从完整百科语料训练通用文本编码器 | prajjwal1/bert-tiny | debug协议通过 | 未执行 |
| GPUv1-B01 | 训练并交付 ImageNet 图像分类模型 | TorchVision ResNet-50 | debug协议通过 | 未执行 |
| GPUv1-B02 | 为开放图像库建立可查询的目标框目录 | TorchVision RetinaNet ResNet50-FPN (COCO category variant) | debug协议通过 | 未执行 |
| GPUv1-B03 | 训练 COCO 实例分割与对象轮廓导出 | TorchVision Mask R-CNN ResNet50-FPN | debug协议通过 | 未执行 |
| GPUv1-B04 | 建立高分辨率城市道路语义分割模型 | nvidia/segformer-b0-finetuned-cityscapes-1024-1024 | debug协议通过 | 未执行 |
| GPUv1-B05 | 生成三维肾脏肿瘤分割与体积结果 | MLPerf KiTS19 reference 3D U-Net inference | 原生资产/环境待补 | 未执行 |
| GPUv1-B06 | 训练驾驶场景三维目标检测并交付空间框 | MMDetection3D CenterPoint nuScenes source recipe | 原生资产/环境待补 | 未执行 |
| GPUv1-B07 | 训练点云语义分类并交付完整扫描标签 | Official Cylinder3D SemanticKITTI | 原生资产/环境待补 | 未执行 |
| GPUv1-B08 | 微调视频动作识别并输出片段目录 | Official VideoMAE ViT Base SSV2 fine tuning | 原生资产/环境待补 | 未执行 |
| GPUv1-B09 | 训练单目标跟踪器并生成连续轨迹 | Official OSTrack GOT10k native adaptation | 原生资产/环境待补 | 未执行 |
| GPUv1-B10 | 训练户外米制深度模型并导出三维点云 | depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf | debug协议通过 | 未执行 |
| GPUv1-C01 | 批量生成可检索的高分辨率图像素材库 | segmind/tiny-sd | debug协议通过 | 未执行 |
| GPUv1-C02 | 完成带掩码图片并保留未编辑区域 | stable-diffusion-v1-5/stable-diffusion-inpainting | debug协议通过 | 未执行 |
| GPUv1-C03 | 保持场景布局的图像风格转换 | lllyasviel/sd-controlnet-canny | debug协议通过 | 未执行 |
| GPUv1-C04 | 从场景脚本生成完整视频素材库 | damo-vilab/text-to-video-ms-1.7b | debug协议通过 | 未执行 |
| GPUv1-C05 | 将静态素材制作成保持主体的动态镜头 | stabilityai/stable-video-diffusion-img2vid | debug协议通过 | 未执行 |
| GPUv1-C06 | 恢复高分辨率视频的缺失区域 | ProPainter official checkpoints | debug协议通过 | 未执行 |
| GPUv1-C07 | 根据旋律和描述生成音乐素材 | facebook/musicgen-small | debug协议通过 | 未执行 |
| GPUv1-C08 | 制作可检索的环境声音素材库 | cvssp/audioldm-s-full-v2 | debug协议通过 | 未执行 |
| GPUv1-C09 | 构建保持参考音色的中英语音素材库 | Qwen/Qwen3-TTS-12Hz-0.6B-Base | debug协议通过 | 未执行 |
| GPUv1-C10 | 从单张参考图制作可渲染的 PBR 三维资产 | stabilityai/TripoSR | debug协议通过 | 未执行 |
| GPUv1-D01 | 部署科研论文阅读服务并生成逐题答案档案 | Qwen/Qwen2.5-0.5B-Instruct | debug协议通过 | 未执行 |
| GPUv1-D02 | 把政府报告语料编成可更新的摘要档案 | Qwen/Qwen2.5-0.5B-Instruct | debug协议通过 | 未执行 |
| GPUv1-D03 | 为代码库上下文建立可调用的跨文件补全工具 | Qwen/Qwen2.5-Coder-0.5B-Instruct | debug协议通过 | 未执行 |
| GPUv1-D04 | 部署自然语言数据库查询工具并交付真实结果表 | Qwen/Qwen2.5-Coder-0.5B-Instruct | debug协议通过 | 未执行 |
| GPUv1-D05 | 把文档图像问题转成可检索的答案台账 | Qwen/Qwen2.5-VL-3B-Instruct | debug协议通过 | 未执行 |
| GPUv1-D06 | 建立长视频内容问答目录 | Qwen/Qwen2.5-VL-3B-Instruct | debug协议通过 | 未执行 |
| GPUv1-D07 | 将混合版式文档解析为可再利用的结构化档案 | Qwen/Qwen2.5-VL-3B-Instruct | debug协议通过 | 未执行 |
| GPUv1-D08 | 为百万级多语言语料生产可更新的语义向量 | sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | debug协议通过 | 未执行 |
| GPUv1-D09 | 把检索候选重排为可复查的证据列表 | cross-encoder/ms-marco-MiniLM-L6-v2 | debug协议通过 | 未执行 |
| GPUv1-D10 | 交付多语言文档翻译包并提供后续翻译接口 | Qwen/Qwen2.5-0.5B-Instruct | debug协议通过 | 未执行 |
| GPUv1-E01 | 构建大规模订单收入与履约分析数据集 | source-native relational GPU processing | debug协议通过 | 未执行 |
| GPUv1-E02 | 生成历史房贷逾期特征仓库 | source-native GPU feature ETL | debug协议通过 | 未执行 |
| GPUv1-E03 | 训练完整 HIGGS 事件分类模型 | XGBoost CUDA hist | debug协议通过 | 未执行 |
| GPUv1-E04 | 构建年度出租车费用回归与审计模型 | XGBoost CUDA regression | debug协议通过 | 未执行 |
| GPUv1-E05 | 构建亿级图像描述子检索索引 | native SIFT1M retrieval debug variant (not a SIFT1B prefix) | debug协议通过 | 未执行 |
| GPUv1-E06 | 为大型视觉向量库生成内容分区 | GPU K-means on real source descriptors | debug协议通过 | 未执行 |
| GPUv1-E07 | 生成大型历史关注图的节点优先级报告 | GPU PageRank on a frozen genuine graph subset | debug协议通过 | 未执行 |
| GPUv1-E08 | 建立全量 Friendster 社区与跨社区连接清单 | GPU community detection on a frozen genuine graph subset | debug协议通过 | 未执行 |
| GPUv1-E09 | 训练异构学术图的主题分类器 | small heterogeneous GNN on real source graph/features | debug协议通过 | 未执行 |
| GPUv1-E10 | 训练缺失引用推荐模型 | small GraphSAGE on real citation graph/features | debug协议通过 | 未执行 |
| GPUv1-F01 | 从宇宙密度体数据训练参数回归模型 | source-native smaller CosmoFlow training budget | debug协议通过 | 未执行 |
| GPUv1-F02 | 建立大气河流与热带气旋识别模型 | source-native smaller DeepCAM training budget | debug协议通过 | 未执行 |
| GPUv1-F03 | 为长蛋白目标构建可复核的结构预测集 | Official OpenFold model_1_ptm structure prediction | 原生资产/环境待补 | 未执行 |
| GPUv1-F04 | 完成催化吸附初态弛豫与能量排序 | OC20 EquiformerV2 153M All+MD relaxation | 原生资产/环境待补 | 未执行 |
| GPUv1-F05 | 推进大型膜蛋白体系并交付动力学分析 | native GROMACS short run; smaller genuinely sourced structure only as a distinct declared debug variant | debug协议通过 | 未执行 |
| GPUv1-F06 | 模拟金属晶体并分析有限温度结构稳定性 | LAMMPS native Ta SNAP Kokkos CUDA | 原生资产/环境待补 | 未执行 |
| GPUv1-F07 | 生成全球天气集合预报及区域风险摘要 | Earth2Studio FCN3 genuine ERA5 ensemble | 原生资产/环境待补 | 未执行 |
| GPUv1-F08 | 将粗分辨率天气数据降尺度为区域集合场 | PhysicsNeMo CorrDiff native Taiwan downscaling | 原生资产/环境待补 | 未执行 |
| GPUv1-F09 | 训练车辆外流场代理并交付阻力预测 | PhysicsNeMo AeroGraphNet DrivAerNet | 原生资产/环境待补 | 未执行 |
| GPUv1-F10 | 预测三维湍流混合层并验证多步演化 | source-native FNO reduced time window on genuine The Well fields | debug协议通过 | 未执行 |

## 待补的12个原生任务

这些任务的完整上游适配器通过源码编译和CLI检查，doctor在缺失资产时返回78。没有真实GPU执行或独立运行正确性证据，其原生评价器也尚未实现/验收。

- GPUv1-A05：训练英语语音到德语文本的翻译模型。文件：`upstream/fairseq/train.py`, `covost2/config_st.yaml`, `covost2/train.tsv`, `covost2/dev.tsv`, `covost2/spm_unigram10000.model`, `covost2/dict.txt`；模块：`fairseq`。
- GPUv1-B05：生成三维肾脏肿瘤分割与体积结果。文件：`reference_model.pt`, `cases.json`, `preprocessed/case_00000.npy`；模块：`torch`, `numpy`。
- GPUv1-B06：训练驾驶场景三维目标检测并交付空间框。文件：`upstream/mmdetection3d/tools/train.py`, `upstream/mmdetection3d/configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py`, `nuscenes/nuscenes_infos_train.pkl`, `nuscenes/nuscenes_infos_val.pkl`, `nuscenes/v1.0-trainval/scene.json`；模块：`mmengine`, `mmcv`, `mmdet3d`。
- GPUv1-B07：训练点云语义分类并交付完整扫描标签。文件：`upstream/Cylinder3D/train_cylinder_asym.py`, `upstream/Cylinder3D/config/semantickitti.yaml`, `SemanticKITTI/sequences/00/velodyne`, `SemanticKITTI/sequences/00/labels`；模块：`spconv`, `torch_scatter`, `yaml`。
- GPUv1-B08：微调视频动作识别并输出片段目录。文件：`upstream/VideoMAE/run_class_finetuning.py`, `videomae_pretrained.pth`, `ssv2/train.csv`, `ssv2/val.csv`, `ssv2/videos`；模块：`timm`, `decord`, `einops`。
- GPUv1-B09：训练单目标跟踪器并生成连续轨迹。文件：`upstream/OSTrack/tracking/train.py`, `upstream/OSTrack/tracking/test.py`, `upstream/OSTrack/experiments/ostrack/vitb_384_mae_ce_32x4_got10k_ep100.yaml`, `mae_pretrain_vit_base.pth`, `GOT10k/train/list.txt`, `GOT10k/val/list.txt`；模块：`timm`, `cv2`, `yaml`, `lmdb`。
- GPUv1-F03：为长蛋白目标构建可复核的结构预测集。文件：`upstream/openfold/run_pretrained_openfold.py`, `model_1_ptm.pt`, `targets.fasta`, `alignments`；模块：`openfold`, `Bio`。
- GPUv1-F04：完成催化吸附初态弛豫与能量排序。文件：`upstream/equiformer_v2/main_oc20.py`, `equiformer_v2_153M_all_md.pt`, `oc20_initial_structures.lmdb`, `relaxation.yml`；模块：`ocpmodels`, `e3nn`, `ase`, `lmdb`。
- GPUv1-F06：模拟金属晶体并分析有限温度结构稳定性。文件：`lammps/bin/lmp`, `lammps/examples/snap/in.snap.Ta06A`, `lammps/potentials/Ta06A.snap`, `lammps/potentials/Ta06A.snapcoeff`, `lammps/potentials/Ta06A.snapparam`；模块：``。
- GPUv1-F07：生成全球天气集合预报及区域风险摘要。文件：`fcn3_checkpoint`, `era5_initial.nc`, `forecast_config.json`；模块：`earth2studio`, `xarray`, `netCDF4`。
- GPUv1-F08：将粗分辨率天气数据降尺度为区域集合场。文件：`corrdiff/regression.mdlus`, `corrdiff/diffusion.mdlus`, `cwa.zarr`, `corrdiff_config.yaml`；模块：`physicsnemo`, `zarr`, `xarray`, `hydra`。
- GPUv1-F09：训练车辆外流场代理并交付阻力预测。文件：`upstream/physicsnemo/examples/cfd/aerographnet/train.py`, `drivaernet/train_manifest.json`, `drivaernet/validation_manifest.json`, `drivaernet/geometry_and_fields`；模块：`physicsnemo`, `dgl`, `pyvista`。

## 回放与评分范围

所有任务侧训练、模型推理、媒体生成、索引和模拟均实际执行。Flash调用在宿主控制器完成，key仅通过stdin读入内存，未写入文件或传入容器。求解器状态、程序退出、debug协议评分、模型质量和正式规模结果分别记录。F10等早期运行的LLM结束事件缺失与可验证产物通过可同时存在；不能把两者混为一个成功标记。

当前评分器用于合作型agent的调试验收：原始求解阶段看不到隐藏标签，交付目录在评分阶段只读；独立标准模型/CPU公式核对原始完整产物，再重放代码或新请求。评分器和重放代码仍在同一评估容器内，尚未完成针对恶意程序的oracle隔离、评分进程权限隔离与抗篡改验证。

资源文件是单次调试的设备总NVML采样和容器统计，采样间隔受docker stats耗时影响；不是每进程显存计账，短任务峰值可能漏采，也不代表冷启动、多GPU、云准入/抢占/迁移实验。

## 交付与复现

review ZIP含60题、60份Flash源码、原始规格/提示、模型和输入锁、48题评价器、容器控制器、来源准备脚本与测得证据；不含模型权重、训练checkpoint、完整媒体、完整思维链或API key。独立的debug_inputs ZIP含冻结真实输入与隐藏oracle；将其解压到review目录。原机的全部模型与执行产物仍保留在 gpu_suite/ 下。

模型权重按 model_locks/ 中的revision和SHA256恢复；restore_models.py负责HF模型，TorchVision/ProPainter及其他来源按各锁的URL补齐。原始prepare脚本中部分数据接口依赖上游当前数据视图，重新运行可能产生新实例；优先使用本次冻结输入包，内容不符时拒绝当作同一实例。

此实现采用挂载Python环境的容器方案，已在本机RTX5090/driver570.124.06验证；跨机器完整冷启动重建尚未验收。默认Transformers5.12，C09/C10用4.57.3兼容官方上游。Torch2.11cu128与CUDA12.8NVRTC通过独立挂载提供；宿主原环境与驱动未更换。现有cuDNN运行库9.17与Torch编译9.19存在RNN版本检查差异，C07明确关闭cuDNN调度并用真实CUDA kernel执行，不能将该兼容方式推广为所有上游环境可用。

```bash
cd gpu60_review_v1
export SBENCH_PYTHON_ENV=/path/to/your/python3.12/venv
docker build -t sbench-gpu-runtime:v1 runtime
python restore_models.py --only Qwen/Qwen2.5-0.5B-Instruct
python run_delivery.py GPUv1-E05 --command "python solution/main.py build --input input --output output"
python grade_task.py GPUv1-E05
```

完整环境的包版本/元数据路径见 runtime/environment_*.json；需要依照版本提供独立的Python环境与pydeps/cuda128deps/compat_deps/qwen_tts_deps/cuda_compat。上述命令假设相应环境、冻结输入与任务模型已恢复，源码包本身不包含这些大体积依赖。
