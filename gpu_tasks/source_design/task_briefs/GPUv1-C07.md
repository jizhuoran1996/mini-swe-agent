# GPUv1-C07 · 根据旋律和描述生成音乐素材

Produce music assets from melody and descriptive briefs

**组别**：图像、视频、音频与三维生成　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`musicgen_melody_large_musiccaps_asset_bank`

**Workflow family**：`melody_conditioned_music_production`

## 任务目标

根据旋律参考和文字要求制作音乐素材库，保留每段素材的参考来源、参数和可播放音频，支持在后续节目中准确选取指定片段。

## 具体来源工作负载

facebook/musicgen-melody-large / AudioCraft generate_with_chroma + google/MusicCaps is_balanced_subset

## 输入与配置

- google/MusicCaps 中 is_balanced_subset=true 的原生记录及其 start_s/end_s 对应合法可用音频
- facebook/musicgen-melody-large 3.3B 权重、EnCodec 和官方旋律条件预处理
- 冻结的逐条 caption、生成时长和声道/采样率要求

## 需要完成的工作

- 核对每条输入音频片段与源坐标，提取实际旋律条件
- 运行本地 MusicGen 生成新音乐，不直接复制原始音频
- 建立原旋律、描述和成品之间的映射并导出音频库

## 交付物

- music/<asset_id>.wav
- music-assets.jsonl
- listening/index.html

## 后续使用与状态

按照冻结节目清单使用已交付素材进行配乐编排，返回时间线和实际混音成品；原始生成素材必须保留。

## 独立验收

- 检查每条记录的音频可解码、长度与采样率
- 重新提取 chroma 和文本/音频特征，依据参考运行校准旋律与内容一致性
- 检查返回音频不是参考片段的简单复制、循环或变速
- 回读节目清单核对混音真正使用了指定素材

## 应拒绝的失败方式

- 只写歌曲描述或生成分数
- 以输入音乐充当生成素材
- 使用不可用 URL 空占任务项
- 反复生成同一条旋律填充数量

## 规模配方

### Debug：仅调通

- **workload**：平衡子集中的固定 4 段、每条保留真实 10 秒旋律
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：完整 is_balanced_subset=true 列表；每个原生片段制作一个固定 10 秒、32 kHz 素材；正式可用音频清单与缺失情况冻结，不静默换样本
- **hardware_target**：T1：单张 48 GiB GPU；3.3B 模型和音频条件路径实测后准入
- **useful_output**：平衡音乐类型的真实生成素材库
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：扩展到 MusicCaps 全部原生记录或按 ID 分片到多卡；不以循环旋律加长充当大输入
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

自回归音频 token 生成和解码产生持续 GPU 工作，旋律条件与音频读写增加输入和输出传输；语料规模来自真实不同片段。

## 资源标签（待画像验证）

- autoregressive_audio
- resident_model
- sustained_gpu_compute
- audio_io

## 设备能力

- CUDA
- FP16_or_FP32

## 后端要求

- 下载并固定 AudioCraft/EnCodec/预处理依赖
- 音频获取在构建阶段完成
- 预留实际 WAV 交付空间

## 回放约束

- 音乐生成模型不能由 recorded LLM response 替代
- 旋律提取、生成时长与采样条件冻结
- 若使用后台生成进程，后续混音等待真实完成事件

## Builder需要实现的部分

- 完成原音频合法获取与逐条哈希清单
- 固定 AudioCraft melody-large 可运行环境
- 建立旋律条件与真实音频产物的独立验证

## 与相关任务的边界

主要交付是受旋律约束的音乐；C08 交付环境声音且无旋律条件，C09 交付精确文字内容的语音。

## 数据血缘

- musiccaps
- musicgen

## 任务范围与条件

- MusicCaps 提供坐标与元数据，并不保证所有原视频永远在线；正式输入构建不能静默跳过缺失资产
- 生成模型可处理音色和音乐结构，但不把精确歌词复现当作其原生能力

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_MUSICGEN] MusicGen official inference and model card — [来源](https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md)；检查位置：musicgen-melody-large; generate_with_chroma; objective evaluation configuration
- [C_MUSICCAPS] MusicCaps dataset — [来源](https://huggingface.co/datasets/google/MusicCaps)；检查位置：train CSV; ytid/start_s/end_s/caption/is_balanced_subset/is_audioset_eval

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
