# GPUv1-C09 · 构建保持参考音色的中英语音素材库

Create bilingual speech assets with consistent reference voices

**组别**：图像、视频、音频与三维生成　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`qwen3tts_seedtts_bilingual_prompt_bank`

**Workflow family**：`reference_conditioned_speech_synthesis`

## 任务目标

把给定中英文文本制作成语音素材，使用每条请求指定的参考音色，保证文字内容可懂、记录可追溯，并能在后续新增台词时继续使用同一音色。

## 具体来源工作负载

Qwen/Qwen3-TTS-12Hz-1.7B-Base + Seed-TTS eval en/meta.lst 与 zh/meta.lst

## 输入与配置

- Seed-TTS eval 英语 en/meta.lst 和普通中文 zh/meta.lst 的全部 3,000 个原生条目
- 各条 reference audio / reference text / target text；ground-truth target audio 仅供验证
- Qwen3-TTS-12Hz-1.7B-Base 和 Qwen3-TTS-Tokenizer-12Hz

## 需要完成的工作

- 正确解析两个语言的元数据和参考音频
- 构建语音条件并本地生成目标正文；对同一参考可复用条件对象
- 导出全部 WAV、文字和参考音色映射，支持后续按音色生成

## 交付物

- speech/<utterance_id>.wav
- utterance-manifest.jsonl
- voice-reference-map.json
- listening/index.html

## 后续使用与状态

对采集前已冻结的补充台词，复用对应参考音色继续生成；返回新音频且保持旧素材可访问，不强制人工拆分固定轮数。

## 独立验收

- 逐项检查有效音频与目标文本和语言匹配
- 使用独立 ASR 对实际音频计算 WER/CER，并计算参考说话人相似度；阈值由本设置参考运行校准
- 检查所有请求独立结果完整，不能复制 reference 或 ground-truth 充当输出
- 对补充台词实际回读并检查文字与音色条件

## 应拒绝的失败方式

- 只提交文本或 TTS 接口代码而不生成音频
- 将所有中文请求读成同一个固定短句
- 拷贝 reference audio 或 benchmark target audio
- 用云 TTS API 隐藏设备执行

## 规模配方

### Debug：仅调通

- **workload**：固定 4 个英文和 4 个中文原生条目
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：完整 en/meta.lst（1,000）加 zh/meta.lst（2,000），生成每条完整 target text；保持原生长度分布
- **hardware_target**：T1：单张 24–48 GiB GPU；模型规模中等，主要观察持续自回归生成和音色条件驻留
- **useful_output**：完整中英正文语音库及可继续使用的参考映射
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：将不同 utterance 分片到多 GPU，或用受控请求到达率服务同一清单；均不新增任务 ID
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

真实音频 token 自回归生成、参考条件提取与解码提供不同于通用 LLM 推理的 GPU 路径；语料通过真实文本数量形成持续工作。

## 资源标签（待画像验证）

- autoregressive_audio
- reusable_condition_state
- resident_model
- variable_length_requests

## 设备能力

- CUDA
- BF16_or_FP16

## 后端要求

- 安装固定 Qwen TTS 与 tokenizer
- GPU attention 实现与 fallback 显式记录
- 如保留常驻 worker，端口和对象句柄由运行时绑定

## 回放约束

- 决策 LLM 回放不会跳过 Qwen TTS 的任务侧生成
- reference condition 以逻辑 voice ID 引用，不能重用旧进程的 Python 指针
- 条件缓存是否保留按真实生命周期记录；不将其等同于可跨后端恢复的 GPU snapshot

## Builder需要实现的部分

- 冻结 Seed-TTS eval 的授权数据包、元数据和目标文本
- 构建可复用条件及音频生成适配器
- 固定独立 ASR/SIM oracle 及不混入资源成本的验证区间

## 与相关任务的边界

精确语音正文、语言和参考说话人是目标；不同于 C07 音乐和 C08 环境音，且不与 A 组的语音模型训练重复。

## 数据血缘

- seedtts_eval
- qwen3tts

## 任务范围与条件

- 不要求复制某个真实人的身份或欺骗性表达；仅使用基准授权音频的既定生成协议
- 官方评估是模型能力来源，本任务用于执行资源覆盖，不把 WER 当作基础设施综合评分

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_QWEN_TTS] Qwen3-TTS — [来源](https://github.com/QwenLM/Qwen3-TTS)；检查位置：Qwen3-TTS-12Hz-1.7B-Base; create_voice_clone_prompt; generate_voice_clone
- [C_SEED_TTS_EVAL] Seed-TTS evaluation data and scripts — [来源](https://github.com/BytedanceSpeech/seed-tts-eval)；检查位置：Dataset: en/meta.lst and zh/meta.lst; WER and SIM evaluation

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
