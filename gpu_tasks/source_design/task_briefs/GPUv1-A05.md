# GPUv1-A05 · 训练英语语音到德语文本的翻译模型

Train an English-speech-to-German-text translator

**组别**：语言、语音与推荐模型训练　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`covost2_en_de_s2t_training`

**Workflow family**：`speech_translation_training`

## 任务目标

以英语录音和配对德语译文训练语音翻译模型，交付可以直接从英语音频生成德语文本的模型，并提交完整测试集译文。

## 具体来源工作负载

CoVoST2 English–German + fairseq s2t_transformer_s ST recipe

## 输入与配置

- Common Voice v4 English 音频与 CoVoST2 en_de TSV 的官方 train/dev/test
- s2t_transformer_s 与 config_st_en_de.yaml
- 来源发布的英语 ASR encoder checkpoint 和匹配词表，仅用作初始化

## 需要完成的工作

- 匹配音频ID、目标译文和分割，构建特征/词表与配置
- 按 ST recipe 执行真实30,000次更新，来源的encoder冻结前1000更新策略保持声明
- 选择并平均来源协议所需checkpoint，生成test_st_en_de译文

## 交付物

- speech_translation.pt、数据配置与词表
- test_translations.jsonl：audio_id及德语预测
- sacrebleu报告、checkpoint lineage和训练清单

## 后续使用与状态

使用交付模型处理另一组冻结英语录音，并对长短音频分别汇总翻译质量，复用先前的模型和特征配置。

## 独立验收

- 独立进程从原始音频运行真实模型，核对音频到译文一一映射
- 全量输出句数/语言配置/顺序正确；独立计算sacreBLEU
- 训练集和测试集严格按CoVoST2划分，质量容差在参考执行后固定
- 确认声学encoder路径真实使用，未用人工transcript调用文本翻译器替代

## 应拒绝的失败方式

- 直接使用参考德语译文或英语transcript进行旁路翻译
- 未训练而仅复制公开ST checkpoint
- 漏掉较长或难解码的音频

## 规模配方

### Debug：仅调通

- **data**：train_st_en_de中固定200个互异音频，测试20个
- **work**：相同声学与翻译架构的数据连通性检查
- **hardware_target**：T1 1×24–48 GiB

### Reference large：正式生产规模

- **data**：完整CoVoST2 English–German官方训练分割；完整test_st_en_de
- **model**：s2t_transformer_s，来源30,000-update ST协议，max_tokens采用en-*建议值
- **output**：可直接处理英语音频的模型及完整德语译文
- **hardware_target**：T3 4–8×40–80 GiB，或单GPU累计梯度的长时任务；工程目标，未测量

### 可选扩展：同一任务的变体

- **data**：同一语言对和完整数据
- **work**：设备数/梯度积累调整保持声明的有效batch；不把新语言当作无审查的ID扩增
- **hardware_target**：T3 8 GPUs

## GPU工作与预期资源形态

声学序列编码、跨语言解码及反向传播共同形成变长序列GPU负载，并伴随真实音频特征和checkpoint状态。

## 资源标签（待画像验证）

- speech_text_alignment
- variable_length
- encoder_decoder_training
- all_reduce
- checkpoint_average

## 设备能力

- CUDA
- mixed_precision
- NCCL optional

## 后端要求

- 固定fairseq历史依赖、音频工具、SentencePiece和sacreBLEU
- 足够存放CommonVoice音频、特征和模型检查点

## 回放约束

- 初始ASR checkpoint需冻结；训练期间的状态转换按实际更新计数执行
- 任务端翻译完全真实，agent的语言模型等待单独回放

## Builder需要实现的部分

- 验证CommonVoice v4可获取性与音频授权路径
- 生成固定en_de manifests并构建离线镜像
- 实现音频旁路防护与重新解码验证

## 与相关任务的边界

输入是语音、输出是另一语言文本，目标不同于A03文本翻译和A04原语言转写。

## 数据血缘

- covost2_en_de

## 任务范围与条件

- Common Voice历史版本的获取渠道需在构建时落实
- 来源项目已归档，需要冻结可运行软件栈

## 来源记录

- [A_COVOST_RECIPE] fairseq CoVoST speech translation example — [来源](https://github.com/facebookresearch/fairseq/blob/main/examples/speech_to_text/docs/covost_example.md)；检查位置：Common Voice v4 preparation; English-to-German ST; s2t_transformer_s; 30,000-update recipe and checkpoint averaging
- [A_COVOST_DATA] CoVoST 2 multilingual speech translation corpus — [来源](https://github.com/facebookresearch/covost)；检查位置：CoVoST2 language-pair TSV files and Common Voice alignment

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
