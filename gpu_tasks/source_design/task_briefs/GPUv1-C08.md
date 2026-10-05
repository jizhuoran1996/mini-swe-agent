# GPUv1-C08 · 制作可检索的环境声音素材库

Build a searchable environmental sound library

**组别**：图像、视频、音频与三维生成　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`stable_audio_open_clotho_sound_library`

**Workflow family**：`environmental_audio_synthesis`

## 任务目标

根据环境声音描述清单制作立体声音效素材，满足逐条长度要求，并交付可按声音事件检索、播放和组合使用的素材目录。

## 具体来源工作负载

stabilityai/stable-audio-open-1.0 / stable-audio-tools + Clotho v2.1 evaluation captions

## 输入与配置

- Clotho v2.1 evaluation 完整文件列表；每条按固定 caption 列选一条描述，保留其真实源时长
- stabilityai/stable-audio-open-1.0 与固定 stable-audio-tools 配置
- 原始参考音频仅由质量验证侧使用，任务侧得到描述和长度

## 需要完成的工作

- 建立一条原生 recording 对应一条制作请求的清单
- 执行真实 text-to-audio diffusion 并输出各条 15–30 秒长度的声音
- 保存采样率、时长、事件描述和可播放索引

## 交付物

- sounds/<recording_id>.wav
- sound-library.jsonl
- audition/index.html

## 后续使用与状态

根据给定的声音事件序列和开始时间，从现有素材组装一段音景并导出混音和引用清单。

## 独立验收

- 核对全部 evaluation recording 的覆盖，五个 caption 不能被当成五个独立源录音
- 检查时长、44.1 kHz、双声道、有限数值与非静音输出
- 从实际音频重算内容一致性和分布质量；阈值用参考生成集校准
- 检查混音的时间线和素材引用确实匹配

## 应拒绝的失败方式

- 下载或复制真实参考录音代替合成
- 全部交付同一噪音或静音
- 只生成极短声音再循环到目标长度
- 把五条同源 caption 计成五种任务

## 规模配方

### Debug：仅调通

- **workload**：固定 4 个不同 evaluation recording 的描述和自然时长
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：Clotho v2.1 evaluation 完整 1,045 个原生录音对应描述；各生成同源时长的 44.1 kHz 立体声音频，使用固定采样步数
- **hardware_target**：T1：单张 24–48 GiB GPU；以持续有效音频生成为主，显存峰值未测
- **useful_output**：覆盖多类真实环境事件的生成音效库及演示音景
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：独立录音分片至多 GPU；扩展到 validation/development 需作为同任务新数据实例并记录源重叠
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

文本编码、音频扩散和高采样率解码提供有意义的持续 GPU 工作与较大音频交付量，不用填充张量凑负载。

## 资源标签（待画像验证）

- audio_diffusion
- resident_model
- gpu_to_host_transfer
- audio_artifact_growth

## 设备能力

- CUDA
- FP16_or_BF16

## 后端要求

- 授权后离线预置 Stable Audio 权重
- 固定音频编码和截取策略

## 回放约束

- Stable Audio 的 T5 编码和扩散属于任务侧真实计算
- 完成包括真实波形生成与文件可读，异步 CUDA 不能提前记完成
- 后续音景操作访问本轮真实声音文件

## Builder需要实现的部分

- 冻结 Clotho v2.1 evaluation 文件清单与单 caption 选择
- 实现长度条件适配和独立音频质量检查
- 将逐资产许可证写入输入构建记录

## 与相关任务的边界

环境声音重在事件和持续时间契约，区别于 C07 的旋律结构和 C09 的文字可懂度。

## 数据血缘

- clotho_v2_1
- stable_audio_open

## 任务范围与条件

- 模型适合环境声音而非长篇音乐或准确歌词，任务不要求这些能力
- 本任务偏持续推理和音频数据量，不宣称单次请求必然占满大显存

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_STABLE_AUDIO] Stable Audio Open 1.0 — [来源](https://huggingface.co/stabilityai/stable-audio-open-1.0)；检查位置：Model Description; stable-audio-tools timing-conditioned generation
- [C_CLOTHO] Clotho v2.1 dataset — [来源](https://zenodo.org/records/4783391)；检查位置：clotho_captions_evaluation.csv; clotho_audio_evaluation.7z; metadata and license description

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
