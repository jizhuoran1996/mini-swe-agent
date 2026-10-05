# GPU任务目录：60个来源派生设计

每行是一个canonical task。规模与GPU配置是拟构建配方，不是已测门槛。点击ID查看完整任务卡；卡片中的来源链接对应具体实现或数据。

## A · 语言、语音与推荐模型训练

全参数/适配训练、优化器与嵌入状态、checkpoint、collective。

| ID | Agent交付目标 | 具体来源 | 正式规模 | 优先级 |
|---|---|---|---|---|
| [GPUv1-A01](task_briefs/GPUv1-A01.md) | 训练可交付的多轮指令对话模型 | Alignment Handbook Zephyr SFT: mistralai/Mistral-7B-v0.1 + HuggingFaceH4/ultrachat_200k train_sft | data: 完整 train_sft，完整 test_sft 保留；最长序列 2048；model: Mistral-7B-v0.1 全参数 SFT，一轮训练；hardware_target: T3 8×80 GiB，单节点 NCCL；工程目标，未测量 | advanced |
| [GPUv1-A02](task_briefs/GPUv1-A02.md) | 训练并验证偏好对齐后的对话模型 | Alignment Handbook Zephyr DPO + corrected HuggingFaceH4/ultrafeedback_binarized train_prefs | data: 完整 61,135 对训练，独立 2,000 对测试；model: 7B policy 全参数 DPO + 冻结参考策略，1 epoch；hardware_target: T3 4–8×80 GiB，NCCL；工程目标，未测量 | advanced |
| [GPUv1-A03](task_briefs/GPUv1-A03.md) | 构建可离线交付的英德机器翻译模型 | fairseq Scaling NMT: WMT16 En-De bpe32k + transformer_vaswani_wmt_en_de_big | data: 完整 WMT16 En-De bpe32k train，newstest2013/2014 原始划分；model: Transformer-big；参考协议：验证 BLEU 连续5次评估无改进或30 epochs 上限，采集后冻结实际更新预算；hardware_target: T3 4–8×40–80 GiB；工程目标，未测量 | standard |
| [GPUv1-A04](task_briefs/GPUv1-A04.md) | 适配大规模语音转写模型并交付转录结果 | SpeechBrain Whisper-large-v3 decoder fine-tuning on LibriSpeech960 | data: 完整960小时官方训练分割，一轮；完整test-clean/test-other；model: Whisper-large-v3，冻结 encoder、训练 decoder；hardware_target: T2 1×80 GiB，或 T3 2×40–80 GiB；工程目标，未测量 | pilot |
| [GPUv1-A05](task_briefs/GPUv1-A05.md) | 训练英语语音到德语文本的翻译模型 | CoVoST2 English–German + fairseq s2t_transformer_s ST recipe | data: 完整CoVoST2 English–German官方训练分割；完整test_st_en_de；model: s2t_transformer_s，来源30,000-update ST协议，max_tokens采用en-*建议值；hardware_target: T3 4–8×40–80 GiB，或单GPU累计梯度的长时任务；工程目标，未测量 | standard |
| [GPUv1-A06](task_briefs/GPUv1-A06.md) | 用大规模无标注音频扩展语音表示模型 | wav2vec2-large + Libri-Light unlab-6k, initialized from official LibriSpeech-only libri960_big.pt | data: 来源定义unlab-6k=small+medium，全量约5770小时，完整一遍；model: Wav2Vec2-Large，从LibriSpeech-only预训练初始化继续训练；预算按唯一输入一遍固定；hardware_target: T3 4–8×80 GiB；工程目标，未测量 | advanced |
| [GPUv1-A07](task_briefs/GPUv1-A07.md) | 训练并交付大表嵌入的点击率模型 | NVIDIA DLRM PyTorch, Criteo Terabyte, frequency threshold FL=3 large configuration | data: 完整来源FL=3 Criteo预处理集合，官方天级切分，一轮训练；model: DLRM large；来源描述约82GB checkpoint量级，实际显存需重测；hardware_target: T3 8×40–80 GiB，NCCL all-to-all；工程目标，未测量 | advanced |
| [GPUv1-A08](task_briefs/GPUv1-A08.md) | 适配70B长报告摘要模型并交付可复用适配器 | MLPerf Llama2-70B LoRA + SCROLLS GovReport; public-asset derivative | data: 完整GovReport train一遍；固定全部公开validation或其声明的完整报告ID集合；model: Llama2-70B BF16 + LoRA r16，8192-token监督上限；hardware_target: T3 8×80 GiB，FSDP/ZeRO与NCCL；工程目标，未测量 | advanced |
| [GPUv1-A09](task_briefs/GPUv1-A09.md) | 训练问答检索双编码器并交付检索表征 | DPR biencoder_nq with nq_train+nq_train_hn1, nq_dev, BERT-base question/context encoders | data: 完整nq_train+nq_train_hn1，完整nq_dev；验证候选池固定为其已发布positive/negative上下文去重全集；model: 来源biencoder_nq 40-epoch协议，维持声明有效batch和平均排名验证；hardware_target: T3 8×32–80 GiB，NCCL；工程目标，未测量 | standard |
| [GPUv1-A10](task_briefs/GPUv1-A10.md) | 从完整百科语料训练通用文本编码器 | NVIDIA BERT large two-phase pretraining + Wikimedia Wikipedia 20231101.en | data: 完整20231101.en文章库扣除固定article-ID保留集，约6.4M文章的来源规模；model: BERT-large来源两阶段结构和更新预算7038+1563；语料版本为THENAME派生替换；hardware_target: T3 8×80 GiB，NCCL；工程目标，未测量 | advanced |

## B · 视觉理解、分割与三维感知

高分辨率输入、反向传播、3D张量、主机供数和产物输出。

| ID | Agent交付目标 | 具体来源 | 正式规模 | 优先级 |
|---|---|---|---|---|
| [GPUv1-B01](task_briefs/GPUv1-B01.md) | 训练并交付 ImageNet 图像分类模型 | TorchVision references/classification/train.py; ResNet-50; ILSVRC2012/ImageNet-1K train and validation splits; reference 90-epoch recipe. | data: 完整 ImageNet-1K train；完整 validation；model_config: ResNet-50，90-epoch 源配方；保持参考全局 batch 和学习率语义；hardware_target: T3：单节点 4–8 张 24–48 GiB GPU，NCCL 数据并行；工程目标未实测 | standard |
| [GPUv1-B02](task_briefs/GPUv1-B02.md) | 为开放图像库建立可查询的目标框目录 | MMDetection OpenImages V6 RetinaNet R50-FPN: configs/openimages/retinanet_r50_fpn_32xb2-1x_openimages.py and matching published checkpoint. | data: 完整 OpenImages V6 validation 检测图像清单；不以几百张 calibration 子集代替；model_config: 600 类 RetinaNet R50-FPN 发布配置和 checkpoint，保留声明分辨率/阈值；hardware_target: T1：单张 24–48 GiB GPU；GPU 常驻推理与完整批量输出，未实测 | pilot |
| [GPUv1-B03](task_briefs/GPUv1-B03.md) | 训练 COCO 实例分割与对象轮廓导出 | Detectron2 configs/COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml; COCO train2017/val2017; ImageNet R50 backbone initialization. | data: 完整 COCO train2017 和 val2017；model_config: R50-FPN 3x；270000 iterations，源有效 batch 和调度语义；hardware_target: T3：4–8 张 24–48 GiB GPU；数据并行；工程目标未测 | standard |
| [GPUv1-B04](task_briefs/GPUv1-B04.md) | 建立高分辨率城市道路语义分割模型 | MMSegmentation segformer_mit-b2_8xb1-160k_cityscapes-1024x1024.py; Cityscapes fine train/val; MiT-B2 initialization. | data: 完整 Cityscapes fine train 和完整 val；model_config: MiT-B2，1024x1024 训练裁剪，160000-iteration 源 schedule；hardware_target: T3：8 张 24–48 GiB GPU，或经参考校准的等效 batch 适配；未实测 | advanced |
| [GPUv1-B05](task_briefs/GPUv1-B05.md) | 生成三维肾脏肿瘤分割与体积结果 | MLPerf Inference KiTS19 3D U-Net PyTorch CUDA workload; official 42-case accuracy set and matching reference model/preprocessing. | data: 完整源定义 42-case accuracy 集，每例完整 CT 体；model_config: 匹配的 3D U-Net，冻结滑窗与合并策略；hardware_target: T1：单张 24–48 GiB GPU；逐例加载完整输入并执行 3D patch 推理；目标未测 | pilot |
| [GPUv1-B06](task_briefs/GPUv1-B06.md) | 训练驾驶场景三维目标检测并交付空间框 | MMDetection3D CenterPoint configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py; nuScenes v1.0-trainval. | data: 完整 nuScenes v1.0-trainval 的源 train/val 场景与声明 sweeps；model_config: 0.075 voxel CenterPoint；20-epoch 源配置；hardware_target: T3：8 张 24–48 GiB GPU；NCCL 数据并行和 CUDA 稀疏算子；未实测 | standard |
| [GPUv1-B07](task_briefs/GPUv1-B07.md) | 训练点云语义分类并交付完整扫描标签 | Cylinder3D official config/semantickitti.yaml and train.sh; SemanticKITTI single-scan semantic segmentation; official semantic-kitti-api evaluator. | data: 完整官方 train 扫描及完整序列 08；model_config: 源 single-scan Cylinder3D 配置；构建时解析并冻结完整源训练计划；hardware_target: T2：单张 80 GiB GPU，或 T3 2–4 GPU 经校准适配；未实测 | advanced |
| [GPUv1-B08](task_briefs/GPUv1-B08.md) | 微调视频动作识别并输出片段目录 | VideoMAE ViT-Base SSV2 source recipe: scripts/ssv2/videomae_vit_base_patch16_224_tubemasking_ratio_0.9_epoch_2400/finetune.sh; 174 classes; 16 frames; 30-epoch fine-tuning. | data: 完整 SSV2 源 train/val 视频清单；model_config: ViT-Base 16-frame/224，30-epoch fine-tuning；复用现成预训练 encoder；hardware_target: T3：8 张 40–80 GiB GPU；源脚本为 64 GPU，8-GPU 适配保持有效 batch 并重新校准；未实测 | advanced |
| [GPUv1-B09](task_briefs/GPUv1-B09.md) | 训练单目标跟踪器并生成连续轨迹 | OSTrack official GOT-10k config vitb_384_mae_ce_32x4_got10k_ep100; MAE ViT-Base initialization; GOT-10k train and validation. | data: 完整 GOT-10k source train 和 val；保留原始完整序列；model_config: vitb_384_mae_ce_32x4_got10k_ep100，源 100 epochs；hardware_target: T3：4 张 24–48 GiB GPU 的训练目标；推理可单 GPU 持有模型，未实测 | standard |
| [GPUv1-B10](task_briefs/GPUv1-B10.md) | 训练户外米制深度模型并导出三维点云 | Depth Anything V2 metric_depth/train.py --dataset vkitti --encoder vitl; dataset/splits/vkitti2/train.txt and dataset/splits/kitti/val.txt; 40-epoch default. | data: 完整源 VKITTI2 train.txt 与完整 KITTI val.txt；model_config: ViT-L metric depth；518 crop、40 epochs、户外 80m；source split frozen；hardware_target: T3：4–8 张 40–80 GiB GPU 或经校准单张 80 GiB 方案；未实测 | standard |

## C · 图像、视频、音频与三维生成

持续生成、大模型驻留、媒体处理与产物增长。

| ID | Agent交付目标 | 具体来源 | 正式规模 | 优先级 |
|---|---|---|---|---|
| [GPUv1-C01](task_briefs/GPUv1-C01.md) | 批量生成可检索的高分辨率图像素材库 | MLPerf Inference text_to_image / Stable Diffusion XL 1.0 / 官方 COCO 2014 5,000-sample 输入配置 | workload: 官方 5,000 个 COCO 2014 样本，各生成一张 1024×1024 图；完整推理配置冻结；hardware_target: T1：单张 24–48 GiB CUDA GPU；工程目标，非本包实测 | pilot |
| [GPUv1-C02](task_briefs/GPUv1-C02.md) | 完成带掩码图片并保留未编辑区域 | FLUX.1-Fill-dev + BrushBench 官方 mapping_file.json / inpainting_mask（inside-mask 条目；受损输入由 builder 从源图按掩码派生） | workload: BrushBench 全部正式 inside-mask 条目；逐图保留其自然分辨率或按已声明尺寸策略约束长边，50 步作为待固定的源示例起点；hardware_target: T2：单张 80 GiB GPU；权重/编码器驻留与 offload 策略在画像前确定 | standard |
| [GPUv1-C03](task_briefs/GPUv1-C03.md) | 保持场景布局的图像风格转换 | FLUX.1-Canny-dev / FluxControlPipeline + COCO 2017 val images 与 captions | workload: COCO val2017 全部 5,000 张独立照片；长边按目标 1024 像素且保持比例，固定单一风格与采样协议；hardware_target: T2：单张 80 GiB GPU；工程目标，非已测最低配置 | standard |
| [GPUv1-C04](task_briefs/GPUv1-C04.md) | 从场景脚本生成完整视频素材库 | Wan2.2-T2V-A14B / generate.py --task t2v-A14B + VBench vbench/VBench_full_info.json | workload: VBench 标准去重场景全集；每场景一个 1280×720、81 帧视频，按官方模型配置固定帧率；不以多种子扩充任务数；hardware_target: T2：单张 80 GiB GPU；先沿用官方单卡 offload 示例校准 | advanced |
| [GPUv1-C05](task_briefs/GPUv1-C05.md) | 将静态素材制作成保持主体的动态镜头 | Tencent-Hunyuan/HunyuanVideo-I2V / sample_image2video.py + VBench-I2V vbench2_i2v_full_info.json | workload: 官方 I2V full_info 中全部去重的 image/prompt 对；每项 720p、129 帧，精度及 scheduler 用固定官方配置；hardware_target: T2：单张 80 GiB GPU；官方 720p 表给出约 60 GB 峰值，仍需本环境实测 | advanced |
| [GPUv1-C06](task_briefs/GPUv1-C06.md) | 恢复高分辨率视频的缺失区域 | ProPainter Releases V0.1.0 / datasets/davis/test.json 与发布 test_masks + DAVIS 2017 Full-Resolution TrainVal | workload: ProPainter 官方 DAVIS test list 全集、完整帧；使用 DAVIS full-resolution 源，长边上限 1280，禁止对低分辨率源人为放大；fp16、subvideo_length=80 作为固定起点；hardware_target: T1：单张 48 GiB GPU；窗口/分辨率需先校准，非固定模型参数量代表其峰值 | pilot |
| [GPUv1-C07](task_briefs/GPUv1-C07.md) | 根据旋律和描述生成音乐素材 | facebook/musicgen-melody-large / AudioCraft generate_with_chroma + google/MusicCaps is_balanced_subset | workload: 完整 is_balanced_subset=true 列表；每个原生片段制作一个固定 10 秒、32 kHz 素材；正式可用音频清单与缺失情况冻结，不静默换样本；hardware_target: T1：单张 48 GiB GPU；3.3B 模型和音频条件路径实测后准入 | standard |
| [GPUv1-C08](task_briefs/GPUv1-C08.md) | 制作可检索的环境声音素材库 | stabilityai/stable-audio-open-1.0 / stable-audio-tools + Clotho v2.1 evaluation captions | workload: Clotho v2.1 evaluation 完整 1,045 个原生录音对应描述；各生成同源时长的 44.1 kHz 立体声音频，使用固定采样步数；hardware_target: T1：单张 24–48 GiB GPU；以持续有效音频生成为主，显存峰值未测 | pilot |
| [GPUv1-C09](task_briefs/GPUv1-C09.md) | 构建保持参考音色的中英语音素材库 | Qwen/Qwen3-TTS-12Hz-1.7B-Base + Seed-TTS eval en/meta.lst 与 zh/meta.lst | workload: 完整 en/meta.lst（1,000）加 zh/meta.lst（2,000），生成每条完整 target text；保持原生长度分布；hardware_target: T1：单张 24–48 GiB GPU；模型规模中等，主要观察持续自回归生成和音色条件驻留 | standard |
| [GPUv1-C10](task_briefs/GPUv1-C10.md) | 从单张参考图制作可渲染的 PBR 三维资产 | Tencent Hunyuan3D-2.1 shape + paint pipeline / Google Scanned Objects 1,030-object collection | workload: 全部 1,030 个 GSO 物体，各一张固定真实渲染视图；逐物体执行官方形状与纹理生成，paint max_num_view=6/resolution=512 起点，保存完整资产；hardware_target: T1：单张 48 GiB GPU；官方组合管线示例约 29 GB，具体 peak 待本环境实测 | standard |

## D · 任务侧模型推理与检索处理

32B/72B权重、长上下文、prefill/decode、常驻服务。

| ID | Agent交付目标 | 具体来源 | 正式规模 | 优先级 |
|---|---|---|---|---|
| [GPUv1-D01](task_briefs/GPUv1-D01.md) | 部署科研论文阅读服务并生成逐题答案档案 | LongBench qasper test（完整 200 条），Qwen/Qwen2.5-32B-Instruct；保留原始论文上下文和问题 | data: qasper test 全 200 条，不复制扩充；model: Qwen2.5-32B-Instruct，BF16，完整上下文；依据官方 long-text 说明固定上下文配置；hardware_target: T3：2×80 GiB GPU，模型并行；这是构建目标而非实测最低配置 | standard |
| [GPUv1-D02](task_briefs/GPUv1-D02.md) | 把政府报告语料编成可更新的摘要档案 | LongBench gov_report test 全 200 份报告，Qwen/Qwen2.5-32B-Instruct | data: gov_report test 全 200 份原报告；model: Qwen2.5-32B-Instruct，BF16；long-text 配置按模型卡固定；hardware_target: T3：2×80 GiB GPU，模型并行 | standard |
| [GPUv1-D03](task_briefs/GPUv1-D03.md) | 为代码库上下文建立可调用的跨文件补全工具 | LongBench repobench-p test 全 500 条，Qwen/Qwen2.5-Coder-32B-Instruct | data: repobench-p test 全 500 条；model: Qwen2.5-Coder-32B-Instruct，BF16；模板和结束规则冻结；hardware_target: T2：单 80 GiB GPU 为构建目标；建包时用最长输入验证容量，必要的 T3 profile 单独冻结 | standard |
| [GPUv1-D04](task_briefs/GPUv1-D04.md) | 部署自然语言数据库查询工具并交付真实结果表 | birdsql/bird_sql_dev_20251106 的 dev_20251106 全 1,534 条，11 个对应 SQLite 数据库，Qwen2.5-Coder-32B-Instruct | data: 2025-11-06 清洗版 dev 全 1,534 问题和对应 11 个真实数据库；model: Qwen2.5-Coder-32B-Instruct，BF16；hardware_target: T2：单 80 GiB GPU，配足数据库和结果盘 | standard |
| [GPUv1-D05](task_briefs/GPUv1-D05.md) | 把文档图像问题转成可检索的答案台账 | 原始 DocVQA 单页 validation 全集，Qwen2.5-VL-32B-Instruct；使用官方来源图像和问题，不用 DocVQA2026 小样本替代 | data: 原始 DocVQA validation 完整问题及所有对应页面；builder 从官方清单冻结确切数量和哈希；model: Qwen2.5-VL-32B-Instruct，BF16；像素预算遵循并固定官方 processor 设置；hardware_target: T2：单 80 GiB GPU 为起点；完整形状容量在建包时验证 | standard |
| [GPUv1-D06](task_briefs/GPUv1-D06.md) | 建立长视频内容问答目录 | Video-MME 官方全量 900 视频 /2,700 QA，Qwen2.5-VL-72B-Instruct，本地视频输入与 subtitle-free 固定协议 | data: 全 900 视频与 2,700 题，包含真实 30–60 分钟视频；每个问题执行一次；model: Qwen2.5-VL-72B-Instruct，BF16；subtitle-free；全时间轴含首尾均匀 max128frames、每帧≤448×448、视觉tokens≤32768、总输入≤40960、生成≤512；max_position_embeddings=65536 的长视频配置按模型卡建议在参考画像前验证锁定。；hardware_target: T3：4×80 GiB GPU，NCCL/tensor-parallel 能力与足够媒体存储 | advanced |
| [GPUv1-D07](task_briefs/GPUv1-D07.md) | 将混合版式文档解析为可再利用的结构化档案 | OmniDocBench 全 1,651 页，v1.7 评估协议对应的数据快照，Qwen2.5-VL-72B-Instruct | data: 全量 1,651 页；v1.7 evaluator 与数据内容 hash 同时冻结；model: Qwen2.5-VL-72B-Instruct，BF16，固定页面像素预算与生成结束规则；hardware_target: T3：4×80 GiB GPU | advanced |
| [GPUv1-D08](task_briefs/GPUv1-D08.md) | 为百万级多语言语料生产可更新的语义向量 | MIRACL ar 与 hi 全部段落及 dev 查询；Qwen/Qwen3-Embedding-8B，4,096 维输出 | data: ar+hi 完整语料共 2,567,678 个原始段落与对应 dev 查询；model: Qwen3-Embedding-8B，BF16 前向，4,096 维；输出 dtype 在 manifest 冻结；hardware_target: T1：单 48 GiB GPU，充足主存和向量输出盘；可持续运行，时间待画像 | pilot |
| [GPUv1-D09](task_briefs/GPUv1-D09.md) | 把检索候选重排为可复查的证据列表 | BEIR nq test 全 3,452 查询；从全 2.68M 语料冻结的每题 top-100 BM25 候选；Qwen3-Reranker-8B | data: 3,452 查询，每题固定 100 个真实候选，共 345,200 对；候选生成使用完整原语料；model: Qwen3-Reranker-8B，BF16，官方联合编码打分；输入截断规则冻结；hardware_target: T1：单 48 GiB GPU | pilot |
| [GPUv1-D10](task_briefs/GPUv1-D10.md) | 交付多语言文档翻译包并提供后续翻译接口 | google/wmt24pp 的 en-de_DE、en-fr_FR、en-es_MX、en-it_IT、en-ja_JP、en-ko_KR、en-zh_CN、en-ru_RU 全部有效行；CohereLabs/aya-expanse-32b | data: 八个具名 WMT24++ 配置的全部非 bad-source 行；每行翻译一次，确切 ID 列表在建包时冻结；model: CohereLabs/aya-expanse-32b，BF16；整文档段落结构保留，冻结提示和解码；hardware_target: T2：单 80 GiB GPU | standard |

## E · GPU数据、向量与图计算

大表连接、图/索引驻留、host-device传输、spill及多GPU通信。

| ID | Agent交付目标 | 具体来源 | 正式规模 | 优先级 |
|---|---|---|---|---|
| [GPUv1-E01](task_briefs/GPUv1-E01.md) | 构建大规模订单收入与履约分析数据集 | cuDF-Polars PDS-H; tpchgen-cli SF1000; lineitem/orders/customer/supplier/part/partsupp/nation/region tables; source query families Q5/Q9/Q12 | workload: SF1000 全套原生生成表，一次完成三个互相关联报表；使用 GPU streaming engine；proposed_hardware_tier: T2：单 80GiB GPU，工程目标配足主机内存、NVMe 输入/临时空间；不要求全表驻留显存 | pilot |
| [GPUv1-E02](task_briefs/GPUv1-E02.md) | 生成历史房贷逾期特征仓库 | NVIDIA MortgageETL.ipynb; Fannie Mae primary acquisition cohorts 2000Q1–2003Q4 and associated performance histories, frozen provider release | workload: 2000Q1–2003Q4 全部原生放款批次及其冻结性能历史；完整执行官方 ETL 逻辑；proposed_hardware_tier: T3：2–4×80GiB GPU 的 Spark RAPIDS；主机 RAM、shuffle/NVMe 空间按资产清单规划 | standard |
| [GPUv1-E03](task_briefs/GPUv1-E03.md) | 训练完整 HIGGS 事件分类模型 | UCI HIGGS 11,000,000 rows; XGBoost CUDA histogram training and QuantileDMatrix | workload: 原生全部 11M 事件，10M 训练与各 0.5M 验证/测试；有效 early stopping 后交付模型；proposed_hardware_tier: T1：单 24–48GiB CUDA GPU；这是工程目标，不声称需要占满显存 | pilot |
| [GPUv1-E04](task_briefs/GPUv1-E04.md) | 构建年度出租车费用回归与审计模型 | NVIDIA taxi-gpu.ipynb SparkXGBRegressor; NYC TLC Yellow Taxi 2019 monthly Parquet records | workload: 2019 全部 Yellow Taxi 月度文件；时间切分后完整训练/测试；官方 GPU 回归流程按现代 TLC schema 映射；proposed_hardware_tier: T2：单 80GiB GPU 或固定 2×48GiB Spark GPU worker；主机/NVMe 容量依实际源文件规划 | standard |
| [GPUv1-E05](task_briefs/GPUv1-E05.md) | 构建亿级图像描述子检索索引 | BIGANN/SIFT1B first 100M base descriptors and matching public queries/100M ground truth; Faiss GpuIndexIVFPQ | workload: BIGANN 原生 100M 前缀全量入索引并执行官方 10K 查询；IVF-PQ 的 nlist/code size/nprobe 在参考采集前冻结；proposed_hardware_tier: T2：单80GiB GPU；压缩索引可能在 T1 可行，必须实测决定 | pilot |
| [GPUv1-E06](task_briefs/GPUv1-E06.md) | 为大型视觉向量库生成内容分区 | DEEP1B first 100M 96-D vectors; cuVS K-Means fit/predict with persistent centroids and full assignment output | workload: DEEP1B 前 100M 向量完整拟合/分配；K=4096、一次初始化、按参考收敛规则停止；proposed_hardware_tier: T2：单80GiB GPU，或明确 host-streaming cuVS 路径；不要求所有数据一次复制入显存 | standard |
| [GPUv1-E07](task_briefs/GPUv1-E07.md) | 生成大型历史关注图的节点优先级报告 | LAW twitter-2010 full graph; reverse published message-flow arcs to follower→followed; cuGraph PageRank | workload: twitter-2010全量图；完成收敛计算及完整节点结果导出；proposed_hardware_tier: T3：2–4×80GiB GPU，足够主机 RAM 与 NVMe 解码空间；可行性待画像 | advanced |
| [GPUv1-E08](task_briefs/GPUv1-E08.md) | 建立全量 Friendster 社区与跨社区连接清单 | SNAP com-Friendster full undirected graph and top5000 community annotations; cuGraph distributed Louvain | workload: 完整Friendster图，实际计算分区和跨社区清单；proposed_hardware_tier: T3：4–8×80GiB GPU，主机RAM/临时空间按展开图和双向存储规划 | advanced |
| [GPUv1-E09](task_briefs/GPUv1-E09.md) | 训练异构学术图的主题分类器 | IGBH-large real heterogeneous graph/features; MLPerf retired_benchmarks/rgat/train_rgnn_multi_gpu.py model=rgat, 3 layers, hidden=512, 4 heads, fan_out=15,10,5 | workload: IGBH-large 完整原生图；使用参考脚本的3层RGAT和2个完整epoch上限，验证停止目标由该规模参考校准；不截成几批；proposed_hardware_tier: T3：4×80GiB GPU与充足主机RAM/NVMe；大/全量资产存储超过500GB，容量需预检 | advanced |
| [GPUv1-E10](task_briefs/GPUv1-E10.md) | 训练缺失引用推荐模型 | OGBL-Citation2 full 2,927,963 nodes / 30,561,187 edges; official sampler.py GraphSAGE [15,10,5], three layers, 256 hidden channels | workload: 全量ogbl-citation2，官方GraphSAGE sampler配置；单run默认150epoch上限，参考采集前冻结停止与验证周期；保留完整测试；proposed_hardware_tier: T2：单80GiB GPU或T1采样路径，主机RAM用于图/特征；绝不把所有邻域一次放入显存 | standard |

## F · 科学机器学习与物理计算

大物理域、多步推进、集合计算、科学状态与跨轮续跑。

| ID | Agent交付目标 | 具体来源 | 正式规模 | 优先级 |
|---|---|---|---|---|
| [GPUv1-F01](task_briefs/GPUv1-F01.md) | 从宇宙密度体数据训练参数回归模型 | MLCommons hpc/cosmoflow；cosmoUniverse_2019_05_4parE_tf_v2；128×128×128×4真实模拟裁块。 | data: v2中按源模拟ID做hash排序，选出包含至少32768个不同训练裁块和4096个验证裁块的完整模拟组；冻结实际ID，保持128^3×4。；work: 完成一次预声明的训练阶段并给出完整验证预测；用上游收敛曲线在参考机确定固定更新预算，随后所有后端冻结该预算，不按目标机墙钟截断。；hardware_target: T3：4×80GiB GPU，TensorFlow/Horovod all-reduce；为工程起始目标。 | advanced |
| [GPUv1-F02](task_briefs/GPUv1-F02.md) | 建立大气河流与热带气旋识别模型 | MLCommons hpc/deepcam；CAM5 All-Hist的train/val/test、stats.h5和DeepCAM参考模型。 | data: 从官方train按连续时间块确定4096个不同训练帧，val确定1024帧；按时间块分隔，冻结源文件名与hash。；work: 采用官方DeepCAM模型和训练规则，在参考机校准可交付阶段的更新预算，随后固定更新数并完整生成1024帧验证mask；不使用任意重复帧制造压力。；hardware_target: T3：4×80GiB GPU；PyTorch分布式训练/NCCL。 | advanced |
| [GPUv1-F03](task_briefs/GPUv1-F03.md) | 为长蛋白目标构建可复核的结构预测集 | OpenFold run_pretrained_openfold.py、model_1_ptm；CASP14 H1044、T1050、T1052、T1053、T1061。 | data: 上述5个真实目标全长，不重复序列、不添加填充；至少包括H1044完整2180残基链。；work: 以固定checkpoint和model_1_ptm配置生成每个目标的真实结构；低内存策略先于采集固定。；hardware_target: T2：1×80GiB GPU，允许官方CPU offload并同时计主机成本。 | standard |
| [GPUv1-F04](task_briefs/GPUv1-F04.md) | 完成催化吸附初态弛豫与能量排序 | OC20 IS2RE验证初态；EquiformerV2 153M All+MD检查点；main_oc20.py弛豫路径。 | data: 四个官方验证分区各取SHA256(sid)排序最前128个，共512个不同体系；冻结sid及结构hash。；work: 所有512个体系执行固定优化器的真实力/能量计算及弛豫；物理停止准则和总步数上限写入manifest。；hardware_target: T2：1×80GiB GPU；可按原子数分批，但不改变体系。 | pilot |
| [GPUv1-F05](task_briefs/GPUv1-F05.md) | 推进大型膜蛋白体系并交付动力学分析 | HECBioSim GROMACS 465K hEGFR Dimer (1IVO/1NQL)，465399原子，官方gromacs.tar.xz输入。 | data: 完整465399原子hEGFR dimer，保留全部脂质、水和离子，不裁剪为小蛋白。；work: 1ns真实MD、声明频率的轨迹/能量输出及0.1ns有状态续跑；从TPR的dt计算并冻结步数。；hardware_target: T1：1×24–48GiB GPU与足够宿主CPU；是否部分PME留在CPU先固定。 | pilot |
| [GPUv1-F06](task_briefs/GPUv1-F06.md) | 模拟金属晶体并分析有限温度结构稳定性 | LAMMPS examples/snap/in.snap.Ta06A；potentials/Ta06A.snap、Ta06A.snapcoeff、Ta06A.snapparam；Kokkos GPU。 | data: 按同一物理晶格规则建立32×32×32个BCC晶胞，共65536个相互作用的真实原子；固定密度/周期边界。；work: 沿官方0.5fs时间步推进50ps，即100000步，并完成5ps续跑；数据增大来自物理域，不能复制不相互作用的独立填充。；hardware_target: T1：1×24–48GiB GPU，Kokkos CUDA；工作时长必须画像。 | standard |
| [GPUv1-F07](task_briefs/GPUv1-F07.md) | 生成全球天气集合预报及区域风险摘要 | NVIDIA FCN3官方NGC checkpoint；Earth2Studio FCN3 + NCAR_ERA5 + ensemble；0.25度、6小时步长。 | data: 4个固定真实ERA5初场；模型原生全球0.25度网格；输出5个声明气象量。；work: 每个初场32个不同集合成员，各15天共60步；生成128条物理预报轨迹及数值产物，不重复媒体或输入。；hardware_target: T2：1×80GiB GPU，按成员批次运行；T3可分配独立成员。 | pilot |
| [GPUv1-F08](task_briefs/GPUv1-F08.md) | 将粗分辨率天气数据降尺度为区域集合场 | CorrDiff Taiwan模型；NGC corrdiff_inference_package:1的regression.mdlus与diffusion.mdlus；CWA完整Zarr源。 | data: 官方CWA完整来源中2021-09-10T00:00到2021-09-16T23:00共168个不同小时，原始网格；构建时列举并检查每小时ID。；work: 每小时64个随机集合成员，使用对应版本官方扩散采样步数；完整写出和统计，不人为增加采样步数凑时长。；hardware_target: T2：1×80GiB GPU分批采样；工程起始目标。 | standard |
| [GPUv1-F09](task_briefs/GPUv1-F09.md) | 训练车辆外流场代理并交付阻力预测 | DrivAerNet v1约4000个车辆几何；PhysicsNeMo AeroGraphNet +experiment=drivaernet/agn。 | data: 完整DrivAerNet v1官方train/val/test；采用drivaernet/agn定义的真实表面网格与节点处理。；work: 按来源模型训练阶段达到参考机校准的固定更新数，然后输出整个test split；不得把官方文档只跑2个test sample的演示参数当正式任务。；hardware_target: T3：4×80GiB GPU，数据并行；不是已验证显存下限。 | advanced |
| [GPUv1-F10](task_briefs/GPUv1-F10.md) | 预测三维湍流混合层并验证多步演化 | The Well turbulent_radiative_layer_3D；官方FNO基线、真实train/valid/test及rollout评估。 | data: 完整官方train/valid/test、原生256×128×128空间场；数据应预置本地而非每轮在线流。；work: 参考官方FNO配置完成校准的固定更新阶段，整个test split执行30步自由rollout并计算源vRMSE；官方12小时H100预算仅用于选定阶段，采集后改为冻结实际update/data-order，不按各后端墙钟改变工作。；hardware_target: T2：1×80GiB GPU作为起始参考；使用官方可复现模型和显存策略。 | standard |

