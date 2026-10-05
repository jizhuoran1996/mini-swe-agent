# 主要来源与检查位置

来源核查日期：2026-10-04。这里记录页面、实现和数据的定位；模型、数据、源码及评价器的不可变内容锁定在实例构建阶段完成。相同URL的多条记录可能服务不同组，不代表不同benchmark。

## A_ALIGNMENT_DPO · Alignment Handbook: Zephyr 7B DPO full recipe

- URL：[https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/dpo/config_full.yaml](https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/dpo/config_full.yaml)
- 发布者：Hugging Face
- 检查位置：SFT model initialization; UltraFeedback chosen/rejected; beta 0.01; length 1024; one epoch
- 支持的来源事实：Specifies direct preference optimization with a 7B policy and preference pairs.
- 浏览/文档版本：main
- 不可变revision：null
- 资产许可/访问状态：Handbook code Apache-2.0; model weights separately licensed.

## A_ALIGNMENT_SFT · Alignment Handbook: Zephyr 7B SFT full recipe

- URL：[https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/sft/config_full.yaml](https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/sft/config_full.yaml)
- 发布者：Hugging Face
- 检查位置：Mistral-7B-v0.1; UltraChat train_sft; max_seq_length 2048; one epoch
- 支持的来源事实：Provides a concrete 7B supervised chat training configuration. This pack retains disjoint published train/test splits instead of the current recipe's pooled split policy.
- 浏览/文档版本：main
- 不可变revision：null
- 资产许可/访问状态：Handbook code Apache-2.0; model and dataset licenses must be recorded separately at acquisition.

## A_BERT · NVIDIA BERT for PyTorch

- URL：[https://github.com/NVIDIA/DeepLearningExamples/blob/master/PyTorch/LanguageModeling/BERT/README.md](https://github.com/NVIDIA/DeepLearningExamples/blob/master/PyTorch/LanguageModeling/BERT/README.md)
- 发布者：NVIDIA
- 检查位置：BERT large configuration; Wikipedia preprocessing; 128/512-token phases; scripts/configs/pretrain_config.sh dgxa100-80g_8gpu_fp16
- 支持的来源事实：Dense encoder pretraining, LAMB, checkpointing, and GPU data-parallel execution. Companion source config was read directly: phase1 7,038 updates and phase2 1,563.
- 浏览/文档版本：master; companion configuration inspected via official raw URL
- 不可变revision：null
- 资产许可/访问状态：Source configuration Apache-2.0; dependencies and output model licensing to record at build.

## A_COVOST_DATA · CoVoST 2 multilingual speech translation corpus

- URL：[https://github.com/facebookresearch/covost](https://github.com/facebookresearch/covost)
- 发布者：Meta / CoVoST authors
- 检查位置：CoVoST2 language-pair TSV files and Common Voice alignment
- 支持的来源事实：English–German translations are aligned with source audio and published splits.
- 浏览/文档版本：main; repository archived
- 不可变revision：null
- 资产许可/访问状态：CoVoST translation data CC0; Common Voice v4 audio access and terms independently required.

## A_COVOST_RECIPE · fairseq CoVoST speech translation example

- URL：[https://github.com/facebookresearch/fairseq/blob/main/examples/speech_to_text/docs/covost_example.md](https://github.com/facebookresearch/fairseq/blob/main/examples/speech_to_text/docs/covost_example.md)
- 发布者：Meta / CoVoST and fairseq authors
- 检查位置：Common Voice v4 preparation; English-to-German ST; s2t_transformer_s; 30,000-update recipe and checkpoint averaging
- 支持的来源事实：Provides the speech-to-text translation model, language-pair configurations, training, and test decoding.
- 浏览/文档版本：main; repository archived
- 不可变revision：null
- 资产许可/访问状态：fairseq code and pretrained ASR checkpoint terms must be recorded at build.

## A_DLRM · NVIDIA DLRM for PyTorch

- URL：[https://github.com/NVIDIA/DeepLearningExamples/blob/master/PyTorch/Recommendation/DLRM/README.md](https://github.com/NVIDIA/DeepLearningExamples/blob/master/PyTorch/Recommendation/DLRM/README.md)
- 发布者：NVIDIA
- 检查位置：Criteo day_0..day_22 training; day_23 split; FL=3 large model; one epoch; hybrid parallel all-to-all; test-only reload
- 支持的来源事实：A substantial real-data recommendation workload with source-defined embedding cardinalities and multi-GPU execution.
- 浏览/文档版本：master
- 不可变revision：null
- 资产许可/访问状态：Code and Criteo dataset terms must be checked; no dataset copied into this specification pack.

## A_DPR · Dense Passage Retrieval official repository

- URL：[https://github.com/facebookresearch/DPR](https://github.com/facebookresearch/DPR)
- 发布者：Meta / DPR authors
- 检查位置：train_dense_encoder.py; biencoder_nq; nq_train+nq_train_hn1; nq_dev; BERT-base dual encoder; 40-epoch reference
- 支持的来源事实：Trainable question/document encoders and NQ positive/hard-negative data with checkpoint evaluation.
- 浏览/文档版本：main; repository archived
- 不可变revision：null
- 资产许可/访问状态：Repository states CC-BY-NC 4.0; NQ/Wikipedia component provenance separately retained.

## A_LIBRILIGHT · Libri-Light data preparation and downloads

- URL：[https://github.com/facebookresearch/libri-light/blob/main/data_preparation/README.md](https://github.com/facebookresearch/libri-light/blob/main/data_preparation/README.md)
- 发布者：Meta / Libri-Light creators
- 检查位置：small 577 h + medium 5,193 h form unlab-6k; small+medium+large form unlab-60k; checksums and segmentation
- 支持的来源事实：Source-defined multi-thousand-hour unlabeled audio scales with no repeated-record padding.
- 浏览/文档版本：main; repository archived
- 不可变revision：null
- 资产许可/访问状态：Code MIT; source recording rights and redistribution terms require verification separately.

## A_LIBRISPEECH · LibriSpeech ASR corpus, SLR12

- URL：[https://www.openslr.org/12](https://www.openslr.org/12)
- 发布者：OpenSLR / LibriSpeech creators
- 检查位置：train-clean-100, train-clean-360, train-other-500 and official dev/test archives
- 支持的来源事实：960 hours of labeled training audio with public held-out clean/other splits.
- 浏览/文档版本：current-page
- 不可变revision：null
- 资产许可/访问状态：CC BY 4.0; archive checksums provided.

## A_LLAMA2_MODEL · Meta Llama 2 70B Hugging Face model

- URL：[https://huggingface.co/meta-llama/Llama-2-70b-hf](https://huggingface.co/meta-llama/Llama-2-70b-hf)
- 发布者：Meta
- 检查位置：Concrete public model distribution to be acquired under authorized access for A08
- 支持的来源事实：Binds the initialization to an actual published model distribution.
- 浏览/文档版本：main
- 不可变revision：null
- 资产许可/访问状态：Meta Llama 2 terms and gated access authorization required.

## A_MISTRAL_MODEL · Mistral 7B v0.1 official model card

- URL：[https://huggingface.co/mistralai/Mistral-7B-v0.1](https://huggingface.co/mistralai/Mistral-7B-v0.1)
- 发布者：Mistral AI
- 检查位置：7B base model and tokenizer used by A01
- 支持的来源事实：Binds the initialization to an actual published model distribution.
- 浏览/文档版本：main
- 不可变revision：null
- 资产许可/访问状态：Apache-2.0 as listed by model card; lock artifact revision at build.

## A_MLPERF_LORA · MLPerf Llama2-70B LoRA benchmark README

- URL：[https://github.com/mlcommons/training/blob/master/llama2_70b_lora/README.md](https://github.com/mlcommons/training/blob/master/llama2_70b_lora/README.md)
- 发布者：MLCommons
- 检查位置：Llama2-70B; SCROLLS GovReport; sequence length 8192; LoRA r16 alpha32; eight A100 80GB devices; official raw README inspected
- 支持的来源事实：Concrete large-model fine-tuning source. The MLCommons preprocessed/fused bundle has membership access restrictions; this pack instead specifies public authorized Meta weights and public SCROLLS data.
- 浏览/文档版本：master
- 不可变revision：null
- 资产许可/访问状态：Meta Llama2 license/access authorization required; MLCommons member-only bundle is not required or redistributed.

## A_SCROLLS · SCROLLS benchmark repository

- URL：[https://github.com/tau-nlp/scrolls](https://github.com/tau-nlp/scrolls)
- 发布者：SCROLLS authors / Tel Aviv University
- 检查位置：GovReport long-document summarization; Hugging Face tau/scrolls dataset and evaluation code
- 支持的来源事实：Public long-report summarization inputs and quality evaluation tooling.
- 浏览/文档版本：main
- 不可变revision：null
- 资产许可/访问状态：GovReport data provenance and dataset license must be recorded at acquisition.

## A_ULTRACHAT · UltraChat 200k dataset card

- URL：[https://huggingface.co/datasets/HuggingFaceH4/ultrachat_200k](https://huggingface.co/datasets/HuggingFaceH4/ultrachat_200k)
- 发布者：Hugging Face H4
- 检查位置：train_sft/test_sft conversation splits and messages schema
- 支持的来源事实：Public conversation data for supervised instruction tuning.
- 浏览/文档版本：main
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## A_ULTRAFEEDBACK · UltraFeedback binarized dataset card

- URL：[https://huggingface.co/datasets/HuggingFaceH4/ultrafeedback_binarized](https://huggingface.co/datasets/HuggingFaceH4/ultrafeedback_binarized)
- 发布者：Hugging Face H4
- 检查位置：train_prefs 61,135 pairs; test_prefs 2,000; corrected labels and contamination note
- 支持的来源事实：Defines chosen/rejected preference pairs and independent evaluation split.
- 浏览/文档版本：main; corrected dataset rather than historical uncorrected revision
- 不可变revision：null
- 资产许可/访问状态：Dataset card lists MIT; preserve source attribution and provenance.

## A_WAV2VEC · fairseq wav2vec 2.0 training and model recipes

- URL：[https://github.com/facebookresearch/fairseq/blob/main/examples/wav2vec/README.md](https://github.com/facebookresearch/fairseq/blob/main/examples/wav2vec/README.md)
- 发布者：Meta / wav2vec 2.0 authors
- 检查位置：wav2vec2_large_librivox configuration; LibriSpeech-only large initialization libri960_big.pt; manifest and feature extraction tools
- 支持的来源事实：Self-supervised speech representation learning and an initialization separate from Libri-Light training audio.
- 浏览/文档版本：main; companion large_librivox YAML inspected through official raw URL
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## A_WHISPER_RECIPE · SpeechBrain LibriSpeech transformer and Whisper recipes

- URL：[https://github.com/speechbrain/speechbrain/blob/develop/recipes/LibriSpeech/ASR/transformer/README.md](https://github.com/speechbrain/speechbrain/blob/develop/recipes/LibriSpeech/ASR/transformer/README.md)
- 发布者：SpeechBrain
- 检查位置：Whisper large-v3 decoder fine-tuning for one epoch; train_with_whisper.py and train_hf_whisper.yaml
- 支持的来源事实：Published large-v3 adaptation uses the full LibriSpeech training collection; encoder frozen, decoder trained. YAML defaults to medium.en, so large-v3 override is explicit.
- 浏览/文档版本：develop; companion YAML read from official raw path
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## A_WIKIPEDIA · Wikimedia Wikipedia dataset

- URL：[https://huggingface.co/datasets/wikimedia/wikipedia](https://huggingface.co/datasets/wikimedia/wikipedia)
- 发布者：Wikimedia
- 检查位置：20231101.en snapshot, approximately 6.4 million full articles, document IDs and text
- 支持的来源事实：A fixed public English corpus for the derived BERT pretraining task.
- 浏览/文档版本：20231101.en snapshot; repository main inspected
- 不可变revision：null
- 资产许可/访问状态：Dataset card lists CC BY-SA 3.0/GFDL and links detailed Wikimedia terms.

## A_WMT_NMT · fairseq Scaling Neural Machine Translation

- URL：[https://github.com/facebookresearch/fairseq/blob/main/examples/scaling_nmt/README.md](https://github.com/facebookresearch/fairseq/blob/main/examples/scaling_nmt/README.md)
- 发布者：Meta / fairseq authors
- 检查位置：WMT16 En-De bpe32k data; transformer_vaswani_wmt_en_de_big; newstest2013/2014; checkpoint averaging
- 支持的来源事实：Training and evaluation recipe for a full English–German translation model.
- 浏览/文档版本：main; repository archived
- 不可变revision：null
- 资产许可/访问状态：Code/data terms and availability of the linked prepared corpus need verification before build.

## A_ZEPHYR_SFT_MODEL · Alignment Handbook Zephyr 7B SFT full model

- URL：[https://huggingface.co/alignment-handbook/zephyr-7b-sft-full](https://huggingface.co/alignment-handbook/zephyr-7b-sft-full)
- 发布者：Hugging Face H4 Alignment Handbook
- 检查位置：Public SFT initialization for A02; model card reports 7B BF16 and eight-device training
- 支持的来源事实：Binds the initialization to an actual published model distribution.
- 浏览/文档版本：main
- 不可变revision：null
- 资产许可/访问状态：Model card lists Apache-2.0.

## B_CENTERPOINT · MMDetection3D CenterPoint model zoo

- URL：[https://github.com/open-mmlab/mmdetection3d/blob/main/configs/centerpoint/README.md](https://github.com/open-mmlab/mmdetection3d/blob/main/configs/centerpoint/README.md)
- 发布者：OpenMMLab
- 检查位置：nuScenes configs/checkpoints; point sweeps and evaluation
- 支持的来源事实：CenterPoint predicts 3D boxes, orientation and velocity from nuScenes LiDAR; official configs and checkpoints exist.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_CENTERPOINT_CONFIG · nuScenes CenterPoint voxel config

- URL：[https://github.com/open-mmlab/mmdetection3d/blob/main/configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py](https://github.com/open-mmlab/mmdetection3d/blob/main/configs/centerpoint/centerpoint_voxel0075_second_secfpn_head-circlenms_8xb4-cyclic-20e_nus-3d.py)
- 发布者：OpenMMLab
- 检查位置：0.075 voxel, circle-NMS, 20-epoch config
- 支持的来源事实：Concrete published configuration for full nuScenes 3D detection training.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_CITYSCAPES · Cityscapes dataset overview

- URL：[https://www.cityscapes-dataset.com/dataset-overview/](https://www.cityscapes-dataset.com/dataset-overview/)
- 发布者：Cityscapes dataset authors
- 检查位置：Dataset overview
- 支持的来源事实：Urban street scenes and dense pixel annotations supply a high-resolution segmentation benchmark.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_CYLINDER3D · Cylinder3D official implementation

- URL：[https://github.com/xinge008/Cylinder3D](https://github.com/xinge008/Cylinder3D)
- 发布者：Cylinder3D authors
- 检查位置：SemanticKITTI preparation; config/semantickitti.yaml; train.sh; demo_folder.py
- 支持的来源事实：Official single-scan LiDAR semantic segmentation training, checkpoint, and folder inference workflow.
- 浏览/文档版本：master/current-page
- 不可变revision：null
- 资产许可/访问状态：Code Apache-2.0; SemanticKITTI/KITTI assets require separate terms verification

## B_DEPTHANYTHING · Depth Anything V2 metric depth

- URL：[https://github.com/DepthAnything/Depth-Anything-V2/blob/main/metric_depth/README.md](https://github.com/DepthAnything/Depth-Anything-V2/blob/main/metric_depth/README.md)
- 发布者：Depth Anything authors
- 检查位置：Metric depth models; training; point-cloud export
- 支持的来源事实：ViT-L metric-depth adaptation uses Virtual KITTI 2 outdoors, with meter-valued depth maps and point-cloud conversion.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_DEPTHANYTHING_TRAIN · Depth Anything V2 metric training code

- URL：[https://github.com/DepthAnything/Depth-Anything-V2/blob/main/metric_depth/train.py](https://github.com/DepthAnything/Depth-Anything-V2/blob/main/metric_depth/train.py)
- 发布者：Depth Anything authors
- 检查位置：Argument defaults and vkitti/KITTI train-validation mapping
- 支持的来源事实：Source-defined VKITTI2 train and KITTI validation lists; 518 input size and 40-epoch default schedule.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_DETECTRON · Detectron2 model zoo

- URL：[https://github.com/facebookresearch/detectron2/blob/main/MODEL_ZOO.md](https://github.com/facebookresearch/detectron2/blob/main/MODEL_ZOO.md)
- 发布者：Meta AI / Detectron2
- 检查位置：Common Settings for COCO Models; reproduction entry points
- 支持的来源事实：COCO models train on train2017 and evaluate on val2017; model configs and checkpoints are provided.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_KITS_MLPERF · MLPerf 3D U-Net KiTS19 workload

- URL：[https://docs.mlcommons.org/inference/benchmarks/medical_imaging/3d-unet/](https://docs.mlcommons.org/inference/benchmarks/medical_imaging/3d-unet/)
- 发布者：MLCommons
- 检查位置：Medical Imaging using 3d-unet; PyTorch CUDA execution
- 支持的来源事实：KiTS19 kidney/tumor segmentation has an official PyTorch CUDA inference workflow.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_MASKRCNN_CONFIG · COCO instance segmentation config

- URL：[https://github.com/facebookresearch/detectron2/blob/main/configs/COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml](https://github.com/facebookresearch/detectron2/blob/main/configs/COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml)
- 发布者：Meta AI / Detectron2
- 检查位置：Mask R-CNN R50 FPN 3x config
- 支持的来源事实：Concrete instance-segmentation config enables mask head and uses the 270000-iteration schedule.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_MLPERF_RULES · MLPerf inference benchmark definitions

- URL：[https://github.com/mlcommons/inference_policies/blob/master/inference_rules.adoc](https://github.com/mlcommons/inference_policies/blob/master/inference_rules.adoc)
- 发布者：MLCommons
- 检查位置：Benchmark table: KiTS19 QSL; input/output definitions
- 支持的来源事实：The KiTS19 evaluation workload uses 42 cases; 3D segmentation processes and returns volumetric data.
- 浏览/文档版本：master/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_ML_COMMONS · MLPerf Training reference workload catalogue

- URL：[https://github.com/mlcommons/training](https://github.com/mlcommons/training)
- 发布者：MLCommons
- 检查位置：Historical v4.0 and v5.1 workload tables
- 支持的来源事实：ImageNet/ResNet, OpenImages/RetinaNet and KiTS19/3D U-Net are benchmark workloads; current classic training paths may have moved to retired_benchmarks.
- 浏览/文档版本：master/current-page
- 不可变revision：null
- 资产许可/访问状态：Repository Apache-2.0; dataset/model terms need separate verification

## B_OPENIMAGES · MMDetection OpenImages recipes

- URL：[https://github.com/open-mmlab/mmdetection/blob/main/configs/openimages/README.md](https://github.com/open-mmlab/mmdetection/blob/main/configs/openimages/README.md)
- 发布者：OpenMMLab
- 检查位置：Open Images v6 data preparation; model table; image-level label evaluation notes
- 支持的来源事实：OpenImages V6 detection includes a 600-class hierarchy, box annotations, image-level labels, and a published RetinaNet checkpoint/config.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_OSTRACK · OSTrack official implementation

- URL：[https://github.com/botaoye/OSTrack](https://github.com/botaoye/OSTrack)
- 发布者：OSTrack authors
- 检查位置：Training; GOT-10k evaluation with vitb_384_mae_ce_32x4_got10k_ep100
- 支持的来源事实：Official ViT tracking implementation provides GOT-10k-specific config and sequence prediction outputs.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code MIT; dataset/checkpoint terms need separate verification

## B_RETINANET_CONFIG · OpenImages RetinaNet R50-FPN config

- URL：[https://github.com/open-mmlab/mmdetection/blob/main/configs/openimages/retinanet_r50_fpn_32xb2-1x_openimages.py](https://github.com/open-mmlab/mmdetection/blob/main/configs/openimages/retinanet_r50_fpn_32xb2-1x_openimages.py)
- 发布者：OpenMMLab
- 检查位置：retinanet_r50_fpn_32xb2-1x_openimages.py
- 支持的来源事实：Concrete RetinaNet configuration for OpenImages.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_SEGFORMER · SegFormer Cityscapes config

- URL：[https://github.com/open-mmlab/mmsegmentation/blob/main/configs/segformer/segformer_mit-b2_8xb1-160k_cityscapes-1024x1024.py](https://github.com/open-mmlab/mmsegmentation/blob/main/configs/segformer/segformer_mit-b2_8xb1-160k_cityscapes-1024x1024.py)
- 发布者：OpenMMLab
- 检查位置：MiT-B2 Cityscapes 1024x1024 config and parent reference
- 支持的来源事实：Concrete high-resolution Cityscapes semantic segmentation config with MiT-B2 initialization.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_SEMANTICKITTI_API · SemanticKITTI evaluation API

- URL：[https://github.com/PRBonn/semantic-kitti-api](https://github.com/PRBonn/semantic-kitti-api)
- 发布者：University of Bonn / dataset authors
- 检查位置：Label mapping; evaluation; submission validation
- 支持的来源事实：Point-wise output format, learning-map inversion, ignored labels, official IoU and distance-stratified evaluation.
- 浏览/文档版本：master/current-page
- 不可变revision：null
- 资产许可/访问状态：API MIT; dataset terms need separate verification

## B_TORCHVISION · TorchVision classification reference

- URL：[https://github.com/pytorch/vision/blob/main/references/classification/README.md](https://github.com/pytorch/vision/blob/main/references/classification/README.md)
- 发布者：PyTorch
- 检查位置：ResNet section; default training table; train.py entry point
- 支持的来源事实：ImageNet classification training and evaluation recipes, including ResNet-50 and the published 90-epoch schedule.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_VIDEOMAE · VideoMAE Something-Something V2 fine-tuning recipe

- URL：[https://github.com/MCG-NJU/VideoMAE/blob/main/scripts/ssv2/videomae_vit_base_patch16_224_tubemasking_ratio_0.9_epoch_2400/finetune.sh](https://github.com/MCG-NJU/VideoMAE/blob/main/scripts/ssv2/videomae_vit_base_patch16_224_tubemasking_ratio_0.9_epoch_2400/finetune.sh)
- 发布者：VideoMAE authors
- 检查位置：ViT-Base SSV2 fine-tuning shell script
- 支持的来源事实：Concrete 174-class video action task: 16-frame inputs, 30 fine-tuning epochs, published pretrained-model lineage.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_VIDEOMAE_DATA · VideoMAE dataset preparation

- URL：[https://github.com/MCG-NJU/VideoMAE/blob/main/DATASET.md](https://github.com/MCG-NJU/VideoMAE/blob/main/DATASET.md)
- 发布者：VideoMAE authors
- 检查位置：Something-Something V2 preparation and CSV annotations
- 支持的来源事实：Official video preparation, source split manifests and on-the-fly decoding workflow.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## B_VKITTI2 · Virtual KITTI 2 dataset

- URL：[https://europe.naverlabs.com/proxy-virtual-worlds-vkitti-2/](https://europe.naverlabs.com/proxy-virtual-worlds-vkitti-2/)
- 发布者：NAVER LABS Europe
- 检查位置：Dataset description; Terms of Use
- 支持的来源事实：Synthetic outdoor RGB/depth data with a published non-commercial license.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：CC BY-NC-SA 3.0; non-commercial use only as stated by dataset owner

## C_BRUSHBENCH · BrushNet / BrushBench

- URL：[https://github.com/TencentARC/BrushNet](https://github.com/TencentARC/BrushNet)
- 发布者：Tencent ARC / BrushNet authors
- 检查位置：Data Download; data/BrushBench/mapping_file.json; Evaluation --mask_key inpainting_mask
- 支持的来源事实：Benchmark binds images, text and inside/outside masks, with released evaluation workflow.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Official data request/download route requires accepting dataset terms; verify permitted redistribution.

## C_CLOTHO · Clotho v2.1 dataset

- URL：[https://zenodo.org/records/4783391](https://zenodo.org/records/4783391)
- 发布者：Tampere University Audio Research Group
- 检查位置：clotho_captions_evaluation.csv; clotho_audio_evaluation.7z; metadata and license description
- 支持的来源事实：Real 15–30 second audio-caption pairs with a frozen evaluation split and downloadable original audio.
- 浏览/文档版本：Version 2.1 / DOI 10.5281/zenodo.4783391
- 不可变revision：10.5281/zenodo.4783391
- 资产许可/访问状态：Caption terms mainly non-commercial with attribution; individual Freesound audio licenses recorded in metadata.

## C_COCO · COCO dataset and downloads

- URL：[https://cocodataset.org/#download](https://cocodataset.org/#download)
- 发布者：COCO Consortium
- 检查位置：COCO image-caption dataset; 2017 validation input specification
- 支持的来源事实：Provides image identifiers, image assets and captions for the conditioned-image task.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Image-specific licenses and annotation terms require verification.

## C_DAVIS · DAVIS 2017 dataset

- URL：[https://davischallenge.org/davis2017/code.html](https://davischallenge.org/davis2017/code.html)
- 发布者：DAVIS Challenge organizers
- 检查位置：TrainVal images; 480p and Full-Resolution downloads
- 支持的来源事实：Supplies the real full-resolution video frames used in the restoration input build.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Check DAVIS terms and source-video rights before redistribution.

## C_FLUX_CANNY · FLUX.1 Canny [dev]

- URL：[https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev](https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev)
- 发布者：Black Forest Labs
- 检查位置：Diffusers FluxControlPipeline with CannyDetector
- 支持的来源事实：Official structure-conditioned generation pipeline accepts an edge control image and text.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Gated weight access; verify FLUX.1-dev non-commercial terms for chosen revision.

## C_FLUX_FILL · FLUX.1 Fill [dev]

- URL：[https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev](https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev)
- 发布者：Black Forest Labs
- 检查位置：Model description and FluxFillPipeline image/mask inference example
- 支持的来源事实：12B model supports text-guided masked image completion.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Gated weight access; FLUX.1-dev non-commercial license and acceptable-use terms.

## C_GSO · Google Scanned Objects

- URL：[https://research.google/blog/scanned-objects-by-google-research-a-dataset-of-3d-scanned-common-household-items/](https://research.google/blog/scanned-objects-by-google-research-a-dataset-of-3d-scanned-common-household-items/)
- 发布者：Google Research
- 检查位置：Impact: 1,030 scanned objects; mesh/texture assets; linked Gazebo collection
- 支持的来源事实：Provides textured household-object meshes suitable for generating fixed conditioning and held-out camera views.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Dataset CC-BY 4.0; preserve attribution and exact object archive hashes.

## C_HUNYUAN3D · Hunyuan3D-2.1

- URL：[https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)
- 发布者：Tencent Hunyuan
- 检查位置：Model Zoo; Code Usage; shape generation and Hunyuan3DPaintConfig
- 支持的来源事实：Image-to-shape plus texture pipeline has 3.3B shape and 2B paint models; official combined-memory example is 29 GB.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Tencent Hunyuan 3D 2.1 license; verify regional/commercial and third-party component conditions.

## C_HUNYUAN_I2V · HunyuanVideo-I2V

- URL：[https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V](https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V)
- 发布者：Tencent Hunyuan
- 检查位置：Requirements; sample_image2video.py; first-frame consistency; xDiT parallel inference
- 支持的来源事实：Official 720p image-animation workflow reports 60 GB GPU peak and testing on an 80 GB GPU.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Tencent model license and dependency licenses require asset-level verification.

## C_MLPERF_SDXL · MLPerf Inference SDXL workload and SCC24 guide

- URL：[https://docs.mlcommons.org/inference/benchmarks/text_to_image/reproducibility/scc24/](https://docs.mlcommons.org/inference/benchmarks/text_to_image/reproducibility/scc24/)
- 发布者：MLCommons
- 检查位置：Introduction: SDXL 1.0, COCO 2014 and 5,000-sample workload; source-linked reference implementation
- 支持的来源事实：Official text-to-image workload binds SDXL 1.0 to COCO 2014; the guide distinguishes full and reduced workloads.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code and model/data licenses must be recorded separately; no MLPerf compliance claim for this derivative.

## C_MUSICCAPS · MusicCaps dataset

- URL：[https://huggingface.co/datasets/google/MusicCaps](https://huggingface.co/datasets/google/MusicCaps)
- 发布者：Google
- 检查位置：train CSV; ytid/start_s/end_s/caption/is_balanced_subset/is_audioset_eval
- 支持的来源事实：Provides real music-caption records with source clip coordinates and subset flags.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Caption dataset CC-BY-SA-4.0; original audio acquisition and redistribution rights are separate.

## C_MUSICGEN · MusicGen official inference and model card

- URL：[https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md](https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md)
- 发布者：Meta FAIR
- 检查位置：musicgen-melody-large; generate_with_chroma; objective evaluation configuration
- 支持的来源事实：Official 3.3B text-and-melody conditioned music generator and AudioCraft evaluation path.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code MIT; model weights CC-BY-NC 4.0, verified in the official model card.

## C_PROPAINTER · ProPainter

- URL：[https://github.com/sczhou/ProPainter](https://github.com/sczhou/ProPainter)
- 发布者：NTU S-Lab / ProPainter authors
- 检查位置：Pretrained Releases V0.1.0; Dataset preparation; datasets/davis/test.json; inference_propainter.py
- 支持的来源事实：Video completion uses optical flow and propagation; official test lists, masks and memory-aware window controls are provided.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code/models under NTU S-Lab License 1.0, non-commercial use only.

## C_QWEN_TTS · Qwen3-TTS

- URL：[https://github.com/QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- 发布者：Qwen / Alibaba Cloud
- 检查位置：Qwen3-TTS-12Hz-1.7B-Base; create_voice_clone_prompt; generate_voice_clone
- 支持的来源事实：Local GPU speech generation can reuse reference-voice conditions across requests.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Repository Apache-2.0; model/tokenizer and evaluation assets must each be pinned.

## C_SEED_TTS_EVAL · Seed-TTS evaluation data and scripts

- URL：[https://github.com/BytedanceSpeech/seed-tts-eval](https://github.com/BytedanceSpeech/seed-tts-eval)
- 发布者：ByteDance Speech
- 检查位置：Dataset: en/meta.lst and zh/meta.lst; WER and SIM evaluation
- 支持的来源事实：Publishes 1,000 English and 2,000 Mandarin prompt/target examples for zero-shot speech generation.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Verify benchmark download and underlying Common Voice / DiDiSpeech terms; do not redistribute voices without checking terms.

## C_STABLE_AUDIO · Stable Audio Open 1.0

- URL：[https://huggingface.co/stabilityai/stable-audio-open-1.0](https://huggingface.co/stabilityai/stable-audio-open-1.0)
- 发布者：Stability AI
- 检查位置：Model Description; stable-audio-tools timing-conditioned generation
- 支持的来源事实：Generates stereo 44.1 kHz audio with explicit duration conditioning, up to 47 seconds.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Gated weight access; Stability AI Community License; commercial-use conditions apply.

## C_VBENCH_I2V · VBench-I2V image/prompt bindings

- URL：[https://github.com/Vchitect/VBench/blob/master/vbench2_beta_i2v/vbench2_i2v_full_info.json](https://github.com/Vchitect/VBench/blob/master/vbench2_beta_i2v/vbench2_i2v_full_info.json)
- 发布者：VBench authors
- 检查位置：image_name, prompt_en, dimension and image_type records
- 支持的来源事实：Binds reference images to image-animation and camera-motion requests.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Repository code license does not replace input-image licenses; verify the official Image Suite asset terms.

## C_VBENCH_T2V · VBench standard prompt and evaluation suite

- URL：[https://github.com/Vchitect/VBench](https://github.com/Vchitect/VBench)
- 发布者：VBench authors
- 检查位置：Usage; vbench/VBench_full_info.json; sixteen T2V dimensions
- 支持的来源事实：Publishes prompt identities and automatic generation-quality evaluation components.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Repository Apache-2.0; associated evaluator weights and assets require individual verification.

## C_WAN22 · Wan2.2

- URL：[https://github.com/Wan-Video/Wan2.2](https://github.com/Wan-Video/Wan2.2)
- 发布者：Wan-Video
- 检查位置：Run Text-to-Video Generation: t2v-A14B 1280*720; single-GPU and FSDP/Ulysses paths
- 支持的来源事实：Published large video-generation workflow includes 80 GB single-GPU example and multi-GPU inference.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Verify code, weights and text-encoder asset licenses separately.

## D_AYA32 · Aya Expanse 32B model card

- URL：[https://huggingface.co/CohereLabs/aya-expanse-32b](https://huggingface.co/CohereLabs/aya-expanse-32b)
- 发布者：Cohere Labs
- 检查位置：Supported Languages, How to Use, Model Details, Terms of Use
- 支持的来源事实：32B 多语言模型，包含本任务八种目标语言和本地推理方法。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：CC-BY-NC-4.0 与使用条款；模型文件访问需用户接受条件

## D_BEIR · BEIR heterogeneous retrieval benchmark

- URL：[https://github.com/beir-cellar/beir](https://github.com/beir-cellar/beir)
- 发布者：BEIR authors
- 检查位置：Dataset table nq test 3,452 queries /2.68M corpus; reranking and evaluation examples
- 支持的来源事实：提供 Natural Questions 的检索语料与 qrels，可用于候选集重排。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：BEIR 代码及 NQ 派生数据的许可分别核对

## D_BIRD_DEV20251106 · BIRD-SQL cleaned development release

- URL：[https://huggingface.co/datasets/birdsql/bird_sql_dev_20251106](https://huggingface.co/datasets/birdsql/bird_sql_dev_20251106)
- 发布者：BIRD team
- 检查位置：dev_20251106 split; Dataset Fields; complete database package; 1,534 rows
- 支持的来源事实：明确问题、证据、数据库 ID 与 SQL 标注；1106 是版本日期的一部分。
- 浏览/文档版本：dev_20251106 released 2025-11-06; immutable revision pending
- 不可变revision：null
- 资产许可/访问状态：数据卡 CC-BY-SA-4.0；数据库资产条款仍需逐项核对

## D_DOCVQA · DocVQA dataset

- URL：[https://site.docvqa.org/datasets/docvqa](https://site.docvqa.org/datasets/docvqa)
- 发布者：DocVQA organizers
- 检查位置：DocVQA original document-image QA dataset, linked challenge access
- 支持的来源事实：原始单页文档图像问答任务与数据入口。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：需按原数据访问条款取得图像；本包不再分发

## D_DOCVQA_ADAPTER · Qwen-VL DocVQA evaluation recipe

- URL：[https://github.com/QwenLM/Qwen-VL/blob/master/eval_mm/EVALUATION.md](https://github.com/QwenLM/Qwen-VL/blob/master/eval_mm/EVALUATION.md)
- 发布者：Qwen team
- 检查位置：DocVQA section: original images/annotations, val.jsonl, docvqa_val and evaluate_vqa.py
- 支持的来源事实：提供公开验证集的转换格式与本地评估路径；本包移植到指定 Qwen2.5-VL 模型。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：代码及 DocVQA 图像/标注许可证分别核对

## D_LONGBENCH_EVAL · LongBench evaluation implementation

- URL：[https://github.com/THUDM/LongBench/blob/main/LongBench/eval.py](https://github.com/THUDM/LongBench/blob/main/LongBench/eval.py)
- 发布者：LongBench authors
- 检查位置：dataset2metric: qasper qa_f1_score, gov_report rouge_score, repobench-p code_sim_score
- 支持的来源事实：提供相应输出的自动评分入口。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## D_LONGBENCH_TASKS · LongBench task definitions

- URL：[https://github.com/THUDM/LongBench/blob/main/LongBench/task.md](https://github.com/THUDM/LongBench/blob/main/LongBench/task.md)
- 发布者：LongBench authors
- 检查位置：LongBench/task.md: statistics, task description, task construction; qasper, gov_report, repobench-p
- 支持的来源事实：发布科研论文问答、政府报告摘要和跨文件代码补全的具体配置与样本定义。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：底层语料各自授权需核对；本包只提供规格和来源链接

## D_MIRACL · MIRACL corpora and relevance judgments

- URL：[https://github.com/project-miracl/miracl](https://github.com/project-miracl/miracl)
- 发布者：MIRACL authors
- 检查位置：Corpora table: ar 2,061,414 passages, hi 506,264; dev queries and relevance judgments
- 支持的来源事实：发布多语言段落语料、稳定文档标识和人工相关性标注。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：仓库 Apache-2.0；Wikipedia 派生语料和标注数据卡分别核对

## D_OMNIDOC · OmniDocBench document parsing benchmark

- URL：[https://github.com/opendatalab/OmniDocBench](https://github.com/opendatalab/OmniDocBench)
- 发布者：OpenDataLab
- 检查位置：Updates v1.7; full 1,651 pages; end2end predictions and text/table/formula/reading-order metrics; Qwen2.5-VL-72B model entry
- 支持的来源事实：包含整页解析所需的文本、表格、公式与阅读顺序标注。
- 浏览/文档版本：evaluation v1.7 documentation; full dataset page snapshot 2026-10-04; immutable revision pending
- 不可变revision：null
- 资产许可/访问状态：代码 Apache-2.0；文档数据仅研究用途、非商业；原文档权利单独保留

## D_QWEN32 · Qwen2.5-32B-Instruct model card

- URL：[https://huggingface.co/Qwen/Qwen2.5-32B-Instruct](https://huggingface.co/Qwen/Qwen2.5-32B-Instruct)
- 发布者：Qwen team
- 检查位置：Model details, Quickstart, Processing Long Texts
- 支持的来源事实：32.5B 文本生成模型及本地推理示例，长上下文配置单独说明。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## D_QWENCODER32 · Qwen2.5-Coder-32B-Instruct model card

- URL：[https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct)
- 发布者：Qwen team
- 检查位置：Model details, Quickstart, Processing Long Texts
- 支持的来源事实：发布代码生成模型、tokenizer、模板和本地生成实现。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## D_QWENEMB8 · Qwen3-Embedding-8B model card

- URL：[https://huggingface.co/Qwen/Qwen3-Embedding-8B](https://huggingface.co/Qwen/Qwen3-Embedding-8B)
- 发布者：Qwen team
- 检查位置：Model overview and local SentenceTransformers/Transformers inference; last-token pooling; output dimension
- 支持的来源事实：8B 嵌入模型、查询指令、池化和向量归一化实现。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Apache-2.0

## D_QWENRERANK8 · Qwen3-Reranker-8B model card

- URL：[https://huggingface.co/Qwen/Qwen3-Reranker-8B](https://huggingface.co/Qwen/Qwen3-Reranker-8B)
- 发布者：Qwen team
- 检查位置：Using Transformers: query-document input, yes/no logits, score construction
- 支持的来源事实：8B 联合编码重排模型与本地逐对打分实现。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## D_QWENVL32 · Qwen2.5-VL-32B-Instruct model card

- URL：[https://huggingface.co/Qwen/Qwen2.5-VL-32B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-32B-Instruct)
- 发布者：Qwen team
- 检查位置：Local image inference, batch inference, image resolution and video input examples
- 支持的来源事实：图像与视频输入处理和 GPU 本地生成实现。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Apache-2.0 shown on model card

## D_QWENVL72 · Qwen2.5-VL-72B-Instruct model card

- URL：[https://huggingface.co/Qwen/Qwen2.5-VL-72B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-72B-Instruct)
- 发布者：Qwen team
- 检查位置：Local image/video inference and processing controls; model license; Processing Long Texts: long-video max_position_embeddings may be raised to 64k; YaRN caution
- 支持的来源事实：72B 级多模态模型及实际图像/视频推理路径。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：自定义 Qwen 许可证；需接受适用条款

## D_VIDEO_MME · Video-MME official dataset and evaluation

- URL：[https://github.com/MME-Benchmarks/Video-MME](https://github.com/MME-Benchmarks/Video-MME)
- 发布者：Video-MME authors
- 检查位置：Overview; Dataset; Evaluation Pipeline; output_test_template.json and eval_your_results.py
- 支持的来源事实：900 个视频、2,700 道问题；有长视频、媒体输入和无第三方 LLM 的答案评分。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：仅学术研究；商业使用禁止；未获批准不得再分发或修改媒体；只分发任务规格和下载指引

## D_WMT24PP · WMT24++ human reference translations

- URL：[https://huggingface.co/datasets/google/wmt24pp](https://huggingface.co/datasets/google/wmt24pp)
- 发布者：Google WMT24++ authors
- 检查位置：Language-pair configs, source/target/document_id/segment_id/is_bad_source fields
- 支持的来源事实：提供不同语言对的逐段人工译文和文档标识，建议排除 bad-source 行。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Apache-2.0 shown on dataset card

## E_BIGANN · NeurIPS 2021 Billion-Scale ANN challenge datasets

- URL：[https://big-ann-benchmarks.com/neurips21.html](https://big-ann-benchmarks.com/neurips21.html)
- 发布者：Big ANN benchmark organizers
- 检查位置：Dataset collection and billion-scale nearest-neighbor benchmark links
- 支持的来源事实：Billion-scale ANN data sources and source query/ground-truth protocol.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Dataset-specific terms need verification; no vectors redistributed.

## E_CUVS_DATA · cuVS benchmark datasets

- URL：[https://docs.nvidia.com/cuvs/user-guide/benchmarking-guide/cu-vs-bench-tool/datasets](https://docs.nvidia.com/cuvs/user-guide/benchmarking-guide/cu-vs-bench-tool/datasets)
- 发布者：NVIDIA
- 检查位置：base/query/groundtruth file formats and matching 10M/100M subsets of billion-scale sources
- 支持的来源事实：Concrete vector file and ground-truth bindings; prefixes must match their oracle.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_CUVS_KMEANS · cuVS K-Means guide

- URL：[https://docs.nvidia.com/cuvs/user-guide/api-guides/clustering-guide/k-means](https://docs.nvidia.com/cuvs/user-guide/api-guides/clustering-guide/k-means)
- 发布者：NVIDIA
- 检查位置：fit/predict, centroids and assignments, convergence, host streaming, balanced and multi-GPU links
- 支持的来源事实：GPU clustering and host-streamed fitting support useful collection partitioning.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_FAISS_1G · Indexing 1G vectors

- URL：[https://github.com/facebookresearch/faiss/wiki/Indexing-1G-vectors](https://github.com/facebookresearch/faiss/wiki/Indexing-1G-vectors)
- 发布者：Meta / Faiss maintainers
- 检查位置：BIGANN 128-D SIFT and Deep1B 96-D descriptors; 10M/100M/1B scale usage
- 支持的来源事实：Concrete image-descriptor datasets suitable for substantial indexing workloads.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code MIT; source vector data terms separate.

## E_FAISS_GPU · Faiss on the GPU

- URL：[https://github.com/facebookresearch/faiss/wiki/Faiss-on-the-GPU](https://github.com/facebookresearch/faiss/wiki/Faiss-on-the-GPU)
- 发布者：Meta / Faiss maintainers
- 检查位置：GpuIndexIVFPQ, batched add/search, scratch state, sharding, CPU conversion before index serialization
- 支持的来源事实：GPU indexing/search and persistent application-index export have explicit supported paths.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_FANNIE · Single-Family Loan Performance Data

- URL：[https://capitalmarkets.fanniemae.com/credit-risk-transfer/fannie-mae-single-family-loan-performance-data](https://capitalmarkets.fanniemae.com/credit-risk-transfer/fannie-mae-single-family-loan-performance-data)
- 发布者：Fannie Mae
- 检查位置：Primary acquisition/performance dataset, access link and release information
- 支持的来源事实：Concrete historical loan acquisition and performance source; download access is through Data Dynamics.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Provider-controlled access/terms; acquire legitimately and verify permitted redistribution; no data included.

## E_FRIENDSTER · Friendster social network and communities

- URL：[https://snap.stanford.edu/data/com-Friendster.html](https://snap.stanford.edu/data/com-Friendster.html)
- 发布者：Stanford SNAP
- 检查位置：com-friendster.ungraph.txt.gz, ground-truth communities; 65,608,366 nodes and 1,806,067,135 edges
- 支持的来源事实：Large undirected friendship network with separate overlapping community annotations.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Public dataset with requested source citation; verify redistribution terms.

## E_HIGGS · UCI HIGGS dataset

- URL：[https://archive.ics.uci.edu/dataset/280/higgs](https://archive.ics.uci.edu/dataset/280/higgs)
- 发布者：UCI / Baldi, Sadowski and Whiteson
- 检查位置：11M rows, 28 features, binary event classification, last 500K test examples
- 支持的来源事实：Large physical-event classification dataset with a source-defined held-out test tail.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_IGB · Illinois Graph Benchmark datasets

- URL：[https://github.com/IllinoisGraphBenchmark/IGB-Datasets](https://github.com/IllinoisGraphBenchmark/IGB-Datasets)
- 发布者：Illinois Graph Benchmark authors
- 检查位置：Heterogeneous tiny/small/medium/large/full releases, real features, igb/train_multi_hetero.py, updated full features
- 支持的来源事实：Large heterogeneous academic graphs and GPU GNN training scripts; large/full inputs exceed 500GB storage.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code MIT; ODC-By-1.0 explicitly applies to public IGB data; content-specific rights still require review.

## E_LOUVAIN · Distributed cuGraph Louvain

- URL：[https://docs.nvidia.com/cugraph/latest/api_docs/api/cugraph/cugraph.dask.community.louvain.louvain/](https://docs.nvidia.com/cugraph/latest/api_docs/api/cugraph/cugraph.dask.community.louvain.louvain/)
- 发布者：NVIDIA
- 检查位置：Undirected input requirement, resolution, modularity gain termination, partitions and modularity outputs
- 支持的来源事实：Multi-GPU community detection returns an actual vertex partition.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_MLPERF_RGAT · MLPerf GNN benchmark introduction

- URL：[https://mlcommons.org/2024/06/gnn-for-mlperf-training-v4/](https://mlcommons.org/2024/06/gnn-for-mlperf-training-v4/)
- 发布者：MLCommons
- 检查位置：IGBH-Full workload and Relational GAT benchmark with distributed GPU training
- 支持的来源事实：R-GAT on a large heterogeneous graph is an established benchmark workload.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_MORTGAGE_ETL · MortgageETL notebook

- URL：[https://github.com/NVIDIA/cudf-spark-examples/blob/main/examples/XGBoost-Examples/mortgage/notebooks/python/MortgageETL.ipynb](https://github.com/NVIDIA/cudf-spark-examples/blob/main/examples/XGBoost-Examples/mortgage/notebooks/python/MortgageETL.ipynb)
- 发布者：NVIDIA
- 检查位置：Notebook code cells: raw loan schema, acquisition/performance extraction, delinquency_12, Spark SQLPlugin; raw source also inspected
- 支持的来源事实：GPU ETL constructs historical mortgage features from acquisition and monthly performance records.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Repository Apache-2.0; Fannie Mae inputs have separate access and redistribution conditions.

## E_OGB_CITATION · OGBL-Citation2 task

- URL：[https://ogb.stanford.edu/docs/linkprop/](https://ogb.stanford.edu/docs/linkprop/)
- 发布者：Open Graph Benchmark authors
- 检查位置：ogbl-citation2 node/edge counts, chronological split, missing citation task, 1000 negatives and MRR
- 支持的来源事实：Citation recommendation has a fixed link-prediction task and evaluator.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Dataset ODC-BY according to task documentation.

## E_OGB_GPU · OGBL-Citation2 official GNN examples

- URL：[https://github.com/snap-stanford/ogb/tree/master/examples/linkproppred/citation2](https://github.com/snap-stanford/ogb/tree/master/examples/linkproppred/citation2)
- 发布者：Open Graph Benchmark authors
- 检查位置：README.md, gnn.py and sampler.py fetched from official raw source; CUDA, GraphSAGE, [15,10,5] sampling, source defaults
- 支持的来源事实：Official full-batch and sampled GPU link prediction with OGB evaluation.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Repository code MIT; graph data ODC-BY.

## E_PAGERANK · Distributed cuGraph PageRank

- URL：[https://docs.nvidia.com/cugraph/latest/api_docs/api/cugraph/cugraph.dask.link_analysis.pagerank.pagerank/](https://docs.nvidia.com/cugraph/latest/api_docs/api/cugraph/cugraph.dask.link_analysis.pagerank.pagerank/)
- 发布者：NVIDIA
- 检查位置：Multi-GPU API, dask-cuDF edge partitions, convergence flag and personalization
- 支持的来源事实：GPU graph ranking with explicit convergence and graph orientation requirements.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_PDSH · cuDF-Polars PDS-H benchmark

- URL：[https://docs.nvidia.com/cudf/26.10/cudf_polars/benchmarks/](https://docs.nvidia.com/cudf/26.10/cudf_polars/benchmarks/)
- 发布者：NVIDIA
- 检查位置：PDS-H setup, tpchgen-cli SF1000 generation, spmd/ray frontends, spill and pinned-memory controls
- 支持的来源事实：Official GPU streaming decision-support benchmark, with single- and multi-GPU execution.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_POLARS · Polars GPU engine

- URL：[https://docs.nvidia.com/cudf/latest/cudf_polars/](https://docs.nvidia.com/cudf/latest/cudf_polars/)
- 发布者：NVIDIA
- 检查位置：GPU query plans, fallback behavior, PDS-H/PDS-DS large scale examples
- 支持的来源事实：Unsupported query plans can fall back to CPU; GPU execution must be checked.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## E_RGAT_IMPL · MLPerf R-GAT reference implementation

- URL：[https://github.com/mlcommons/training/tree/master/retired_benchmarks/rgat](https://github.com/mlcommons/training/tree/master/retired_benchmarks/rgat)
- 发布者：MLCommons
- 检查位置：README.md and train_rgnn_multi_gpu.py fetched from official raw source; model=rgat, dataset_size=large/full, 3 layers/512 hidden/4 heads/[15,10,5] sampling, CSC/FP16 and pin_feature
- 支持的来源事实：Official GPU heterogeneous GNN workflow has preprocessing, multi-GPU training and explicit feature-placement options.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code Apache-2.0; IGBH dataset terms separate.

## E_SPARK_EXAMPLES · Spark XGBoost examples

- URL：[https://github.com/NVIDIA/cudf-spark-examples/tree/main/examples/XGBoost-Examples](https://github.com/NVIDIA/cudf-spark-examples/tree/main/examples/XGBoost-Examples)
- 发布者：NVIDIA
- 检查位置：Mortgage and Taxi blueprints; larger upstream datasets required for performance use
- 支持的来源事实：End-to-end GPU ETL/training examples; sample datasets are only convenience inputs.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code Apache-2.0; underlying datasets have separate terms.

## E_TAXI_GPU · Taxi GPU regression notebook

- URL：[https://github.com/NVIDIA/cudf-spark-examples/blob/main/examples/XGBoost-Examples/taxi/notebooks/python/taxi-gpu.ipynb](https://github.com/NVIDIA/cudf-spark-examples/blob/main/examples/XGBoost-Examples/taxi/notebooks/python/taxi-gpu.ipynb)
- 发布者：NVIDIA
- 检查位置：Raw notebook inspected: fare_amount target, SparkXGBRegressor device=cuda, save/load and RMSE evaluation
- 支持的来源事实：Official GPU regression workflow trains, reloads and applies a taxi fare model.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code Apache-2.0; TLC data terms separate.

## E_TLC · NYC TLC Trip Record Data

- URL：[https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
- 发布者：New York City Taxi and Limousine Commission
- 检查位置：Monthly Yellow Taxi Parquet download lists including 2015 and 2019, schema/errata information
- 支持的来源事实：Public monthly taxi trips support full-year training and chronological evaluation.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Public provider downloads; review NYC terms and freeze retrieved files and schemas.

## E_TWITTER · twitter-2010 graph

- URL：[https://law.di.unimi.it/webdata/twitter-2010/](https://law.di.unimi.it/webdata/twitter-2010/)
- 发布者：Laboratory for Web Algorithmics / original crawl authors
- 检查位置：41,652,230 vertices, 1,468,365,182 arcs, raw arc direction and original-ID mapping
- 支持的来源事实：Large directed graph; published arc direction follows message transmission.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Attribution instructions provided; verify graph reuse terms before redistribution.

## E_XGB · XGBoost GPU support

- URL：[https://xgboost.readthedocs.io/en/stable/gpu/index.html](https://xgboost.readthedocs.io/en/stable/gpu/index.html)
- 发布者：XGBoost maintainers
- 检查位置：device=cuda, tree_method=hist, QuantileDMatrix, GPU prediction and distributed execution
- 支持的来源事实：CUDA tree training and prediction with real dataset and histogram state.
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_AEROGRAPHNET · AeroGraphNet for external aerodynamic evaluation

- URL：[https://docs.nvidia.com/physicsnemo/latest/physicsnemo/examples/cfd/external_aerodynamics/aero_graph_net/README.html](https://docs.nvidia.com/physicsnemo/latest/physicsnemo/examples/cfd/external_aerodynamics/aero_graph_net/README.html)
- 发布者：NVIDIA PhysicsNeMo
- 检查位置：DrivAerNet; drivaernet/agn; training and inference
- 支持的来源事实：真实车辆曲面网格输入，压力/壁面剪切/阻力输出，支持GPU数据并行。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_CASP14 · CASP14 target list

- URL：[https://predictioncenter.org/casp14/targetlist.cgi?view_targets=all](https://predictioncenter.org/casp14/targetlist.cgi?view_targets=all)
- 发布者：Protein Structure Prediction Center
- 检查位置：H1044, T1050, T1052, T1053, T1061 and linked sequence/native records
- 支持的来源事实：可绑定真实长序列目标：H1044为2180残基；其他选定目标580–949残基。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_CORRDIFF · PhysicsNeMo CorrDiff

- URL：[https://github.com/NVIDIA/physicsnemo/blob/main/examples/weather/corrdiff/README.md](https://github.com/NVIDIA/physicsnemo/blob/main/examples/weather/corrdiff/README.md)
- 发布者：NVIDIA PhysicsNeMo
- 检查位置：Taiwan dataset; sampling and evaluation; config_generate_taiwan.yaml
- 支持的来源事实：ERA5到台湾高分辨率场；支持回归加扩散、NetCDF输出及科学评分。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Taiwan data CC BY-NC-ND 4.0 as documented; verify redistribution of full data

## F_CORRDIFF_WEIGHTS · CorrDiff inference package v1

- URL：[https://catalog.ngc.nvidia.com/orgs/nvidia/modulus/models/corrdiff_inference_package/1](https://catalog.ngc.nvidia.com/orgs/nvidia/modulus/models/corrdiff_inference_package/1)
- 发布者：NVIDIA NGC
- 检查位置：Version 1 overview; checkpoints and code compatibility hash
- 支持的来源事实：台湾预训练回归和扩散权重；683.9MB包只含小样本，正式任务须用完整CWA数据。
- 浏览/文档版本：NGC model version 1
- 不可变revision：null
- 资产许可/访问状态：Weights Apache-2.0; sample data CC BY-NC-ND 4.0

## F_COSMOFLOW · CosmoFlow TensorFlow Keras reference

- URL：[https://github.com/mlcommons/hpc/blob/main/cosmoflow/README.md](https://github.com/mlcommons/hpc/blob/main/cosmoflow/README.md)
- 发布者：MLCommons / CosmoFlow authors
- 检查位置：README Datasets; raw file retrieved and read with urllib
- 支持的来源事实：真实N-body模拟、128×128×128×4输入、TFRecord预处理和train/val/test。
- 浏览/文档版本：main; raw README read
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_DEEPCAM · DeepCAM climate segmentation reference

- URL：[https://github.com/mlcommons/hpc/blob/main/deepcam/README.md](https://github.com/mlcommons/hpc/blob/main/deepcam/README.md)
- 发布者：MLCommons / DeepCAM authors
- 检查位置：README Dataset; src/deepCam/run_scripts/run_training.sh; raw files retrieved and read
- 支持的来源事实：CAM5+TECA、768×1152×16输入、三类标签和GPU训练脚本。
- 浏览/文档版本：main; raw README and run script read
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_DRIVAERNET · DrivAerNet and DrivAerNet++

- URL：[https://github.com/Mohamedelrefaie/DrivAerNet](https://github.com/Mohamedelrefaie/DrivAerNet)
- 发布者：DrivAerNet authors / MIT DeCoDE Lab
- 检查位置：DrivAerNet_v1; train_val_test_splits; license
- 支持的来源事实：保留原始v1来源和划分；不将新版8150辆车与v1约4000样本混用。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Data CC BY-NC-4.0; code MIT; noncommercial research

## F_EARTH2_ENSEMBLE · Earth2Studio ensemble workflow

- URL：[https://nvidia.github.io/earth2studio/main/examples/01_getting_started/03_ensemble_workflow/](https://nvidia.github.io/earth2studio/main/examples/01_getting_started/03_ensemble_workflow/)
- 发布者：NVIDIA Earth2Studio
- 检查位置：Ensemble batching; output coordinates; checkpointed workflow
- 支持的来源事实：集合成员、输出变量及状态保存可显式管理。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_EQUIFORMER · EquiformerV2

- URL：[https://github.com/atomicarchitects/equiformer_v2](https://github.com/atomicarchitects/equiformer_v2)
- 发布者：EquiformerV2 authors / Atomic Architects
- 检查位置：README Checkpoints; File Structure; main_oc20.py
- 支持的来源事实：提供OC20预训练153M权重、配置和弛豫执行入口。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：Code MIT; OC20 data and pretrained-weight redistribution terms need separate verification

## F_FCN3 · FourCastNet 3: large ensemble weather forecasting

- URL：[https://developer.nvidia.com/blog/fourcastnet-3-enables-fast-and-accurate-large-ensemble-weather-forecasting-with-scalable-geometric-ml/](https://developer.nvidia.com/blog/fourcastnet-3-enables-fast-and-accurate-large-ensemble-weather-forecasting-with-scalable-geometric-ml/)
- 发布者：NVIDIA / FourCastNet3 authors
- 检查位置：Getting started with FCN3; NCAR_ERA5; NetCDF4 ensemble example
- 支持的来源事实：提供FCN3检查点、全球0.25度/6小时预报和官方GPU集合推理接口。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_GROMACS · Getting good performance from mdrun

- URL：[https://manual.gromacs.org/current/user-guide/mdrun-performance.html](https://manual.gromacs.org/current/user-guide/mdrun-performance.html)
- 发布者：GROMACS developers
- 检查位置：GPU configuration; GPU-resident mode; GPU task assignment
- 支持的来源事实：GROMACS支持真实GPU分子动力学及明确的CPU/GPU任务分工。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_HECBIOSIM · HECBioSim HPC Benchmarking Suite

- URL：[https://www.hecbiosim.org/access-hpc/hpc-benchmarking-suite](https://www.hecbiosim.org/access-hpc/hpc-benchmarking-suite)
- 发布者：HECBioSim
- 检查位置：465K hEGFR dimer; raw GROMACS input archive
- 支持的来源事实：提供465399原子的膜蛋白/脂质/水/离子体系及GROMACS输入。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_LAMMPS_INPUT · LAMMPS SNAP tantalum example

- URL：[https://github.com/lammps/lammps/blob/develop/examples/snap/in.snap.Ta06A](https://github.com/lammps/lammps/blob/develop/examples/snap/in.snap.Ta06A)
- 发布者：LAMMPS developers / Sandia
- 检查位置：in.snap.Ta06A and potentials/Ta06A.snap; raw files retrieved and read
- 支持的来源事实：BCC钽、Ta06A SNAP+ZBL势、300K初速度和0.5fs NVE积分。
- 浏览/文档版本：develop; raw files read
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_LAMMPS_KOKKOS · LAMMPS KOKKOS package

- URL：[https://docs.lammps.org/Speed_kokkos.html](https://docs.lammps.org/Speed_kokkos.html)
- 发布者：LAMMPS developers
- 检查位置：GPU execution and GPU-aware communication
- 支持的来源事实：Kokkos提供CUDA/HIP等设备执行；MPI和设备通信配置需固定。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_LAMMPS_SNAP · LAMMPS pair_style snap

- URL：[https://docs.lammps.org/pair_snap.html](https://docs.lammps.org/pair_snap.html)
- 发布者：LAMMPS developers
- 检查位置：Ta06A example; accelerated styles
- 支持的来源事实：SNAP势文件与GPU加速样式的官方语义。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_MLPERF_HPC · MLPerf Training: HPC

- URL：[https://mlcommons.org/benchmarks/training-hpc/](https://mlcommons.org/benchmarks/training-hpc/)
- 发布者：MLCommons
- 检查位置：Benchmarks table; retirement notice
- 支持的来源事实：列明CosmoFlow、DeepCAM、OC20、OpenFold来源；该系列2025年1月退役，仍可复用已发布工作负载。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_OC20 · OC20 dataset and downloads

- URL：[https://facebookresearch.github.io/fairchem/oc20/](https://facebookresearch.github.io/fairchem/oc20/)
- 发布者：FAIR Chemistry / Open Catalyst Project
- 检查位置：S2EF and IS2RE split download instructions
- 支持的来源事实：公开吸附体系及ID/OOD验证划分，可保留结构ID和物理标签。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_OPENFOLD · OpenFold Inference

- URL：[https://openfold.readthedocs.io/en/latest/Inference.html](https://openfold.readthedocs.io/en/latest/Inference.html)
- 发布者：OpenFold Team
- 检查位置：Precomputed alignments; config presets; outputs; long sequence inference
- 支持的来源事实：GPU结构推理可使用固定MSA、长序列分块/卸载，并输出预测结构。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_WELL_BASELINE · The Well benchmark models

- URL：[https://polymathic-ai.org/the_well/benchmarks/](https://polymathic-ai.org/the_well/benchmarks/)
- 发布者：Polymathic AI
- 检查位置：Baseline protocol; pretrained models; VRMSE and rollouts
- 支持的来源事实：FNO等原始基线使用单H100；提供一步及多步rollout评估和模型权重。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

## F_WELL_DATA · The Well: turbulent_radiative_layer_3D

- URL：[https://polymathic-ai.org/the_well/datasets/turbulent_radiative_layer_3D/](https://polymathic-ai.org/the_well/datasets/turbulent_radiative_layer_3D/)
- 发布者：Polymathic AI / dataset authors
- 检查位置：About the data; physical variables; simulation suite
- 支持的来源事实：90条3D物理序列，每条101帧、256×128×128网格，总量约744.6GB。
- 浏览/文档版本：main/documentation/current-page
- 不可变revision：null
- 资产许可/访问状态：needs_verification

