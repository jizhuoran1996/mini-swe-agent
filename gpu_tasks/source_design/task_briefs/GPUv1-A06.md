# GPUv1-A06 · 用大规模无标注音频扩展语音表示模型

Adapt speech representations with large unlabeled audio

**组别**：语言、语音与推荐模型训练　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`wav2vec2_large_librilight_unlab6k_adaptation`

**Workflow family**：`self_supervised_speech_adaptation`

## 任务目标

利用没有转写标签的有声读物扩展已有语音编码器，交付训练后的表示模型和指定评测录音的帧级表示，使后续语音分析能够直接复用这些资产。

## 具体来源工作负载

wav2vec2-large + Libri-Light unlab-6k, initialized from official LibriSpeech-only libri960_big.pt

## 输入与配置

- Libri-Light small.tar+medium.tar，官方unlab-6k约5770小时，去除来源已标明重复书籍集
- 官方LibriSpeech-only Wav2Vec2-Large checkpoint libri960_big.pt
- fairseq wav2vec2_large_librivox模型/对比学习配置；LibriSpeech dev/test及Libri-Light ABX评测资产

## 需要完成的工作

- 按官方VAD输出构造非重复音频片段，进一步按不超过20秒切分并保留所有有效片段；记录book/speaker/时间偏移和真实时长，短尾部按冻结规则处理
- 从声明初始化继续自监督训练；派生协议为完整unlab-6k一遍，固定1e-5学习率及原对比目标，不运行无意义重复音频
- 导出编码器并重新提取保留录音表示，运行ABX表示评测

## 交付物

- speech_encoder.pt和特征提取配置
- heldout_features/及audio_id-to-frame-offset清单
- self_supervised_training_manifest.json与ABX结果

## 后续使用与状态

从保存编码器提取另一批未用于更新的真实录音表示，并按原始音频时间轴给出片段到特征的映射；可保留模型在设备上等待新批次。

## 独立验收

- 重载encoder并从真实音频重算特征；校验帧数、维度、有限数值及非恒定表示
- 核对音频去重、样本覆盖和权重更新
- 独立运行固定ABX评测，与参考校准的稳定范围对照；不凭训练log验收
- 原Libri-Light全量预训练分数不作为本派生continued-training任务的承诺

## 应拒绝的失败方式

- 仅复制初始化encoder或返回预下载embedding
- 循环一个音频文件冒充数千小时
- 将解码/特征提取全部移到grader而agent没有完成训练

## 规模配方

### Debug：仅调通

- **data**：unlab-600中固定100段真实音频，另保留20段
- **work**：同一Large模型与自监督目标的加载和一次小更新检查
- **hardware_target**：T1 1×48 GiB或T2 1×80 GiB

### Reference large：正式生产规模

- **data**：来源定义unlab-6k=small+medium，全量约5770小时，完整一遍
- **model**：Wav2Vec2-Large，从LibriSpeech-only预训练初始化继续训练；预算按唯一输入一遍固定
- **output**：更新后的编码器、完整指定评测表示与ABX报告
- **hardware_target**：T3 4–8×80 GiB；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：来源定义unlab-60k=small+medium+large，不加入duplicate子集
- **work**：同目标全量一遍，独立manifest与长时预算；不照搬原128-GPU百万更新训练作为默认
- **hardware_target**：T3 8 GPUs或另行声明多节点长时场景

## GPU工作与预期资源形态

数千小时真实序列驱动大型声学编码器持续反向传播，保留模型及优化器状态，并覆盖数据加载、特征物化和后续状态复用。

## 资源标签（待画像验证）

- self_supervised_training
- large_audio_corpus
- activation_memory
- host_device_transfer
- retained_encoder
- feature_materialization

## 设备能力

- CUDA
- FP16
- NCCL optional

## 后端要求

- 固定fairseq版本和音频解码栈
- 大输入卷与本轮模型/特征输出空间，声明数据加载缓存

## 回放约束

- 固定实际音频manifest与裁剪随机性；同一后端运行慢时不能减少音频量
- CUDA计算完成后再保存/发布特征，model wait期间允许模型按原轨迹驻留

## Builder需要实现的部分

- 实现从LibriSpeech-only checkpoint到unlab6k的派生继续训练协议
- 锁定去重/分段清单和ABX适配器
- 参考运行验证训练稳定性、质量及GPU成本

## 与相关任务的边界

无标注表示学习与帧级特征交付，不学习A04转写文本或A05翻译文本；初始化和语料也明确不同。

## 数据血缘

- libri_light

## 任务范围与条件

- 继续训练协议由THENAME派生，尚无已验证质量结果
- 语料与来源模型版本需固定；不使用已撤下公开下载的VoxCeleb2作为替代输入

## 来源记录

- [A_WAV2VEC] fairseq wav2vec 2.0 training and model recipes — [来源](https://github.com/facebookresearch/fairseq/blob/main/examples/wav2vec/README.md)；检查位置：wav2vec2_large_librivox configuration; LibriSpeech-only large initialization libri960_big.pt; manifest and feature extraction tools
- [A_LIBRILIGHT] Libri-Light data preparation and downloads — [来源](https://github.com/facebookresearch/libri-light/blob/main/data_preparation/README.md)；检查位置：small 577 h + medium 5,193 h form unlab-6k; small+medium+large form unlab-60k; checksums and segmentation
- [A_LIBRISPEECH] LibriSpeech ASR corpus, SLR12 — [来源](https://www.openslr.org/12)；检查位置：train-clean-100, train-clean-360, train-other-500 and official dev/test archives

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
