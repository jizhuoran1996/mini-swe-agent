# GPUv1-D06 · 建立长视频内容问答目录

Build a long-video question-answer catalog

**组别**：任务侧模型推理与检索处理　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`video_mme_full_answer_catalog`

**Workflow family**：`long_video_understanding`

## 任务目标

对给定视频库建立问答目录，回答来源问题并保存视频标识、采样时间点与预测；长视频必须覆盖完整时间轴，不能只看开头。

## 具体来源工作负载

Video-MME 官方全量 900 视频 /2,700 QA，Qwen2.5-VL-72B-Instruct，本地视频输入与 subtitle-free 固定协议

## 输入与配置

- 官方 Video-MME 媒体、问题与独立答案；下载后哈希冻结
- Qwen2.5-VL-72B-Instruct 和 qwen-vl-utils/processor
- 视频解码后端、时间采样与像素预算配置
- 派生默认输入预算：全时间轴均匀取不超过 128 个不同帧并含首尾；每帧宽/高均不超过 448、面积不超过 448×448；实际视觉 token≤32768、总输入 token≤40960、max_new_tokens=512。

## 需要完成的工作

- 校验视频可解码且问题映射完整
- 按固定规则从整段视频抽帧并在 GPU 上真正编码、回答
- 保存实际采样时间戳、输入长度、题目答案和逐视频完成状态
- 保存实际 processor 输出的视觉/总 token 计数、帧尺寸和时间戳；超预算显式报 input_budget_exceeded，不截视频尾部或临时改采样规则。

## 交付物

- video_answers.json
- sampled_timestamps.jsonl
- video_input_manifest.json
- completion_states.jsonl

## 后续使用与状态

继续分析 manifest 后半部分视频，保留已加载模型与完成清单；最终合并全部视频的内容问答目录。

## 独立验收

- 视频与问题 ID 全覆盖；抽查采样落在声明时间范围且不重复填充
- 用官方 eval_your_results.py 复算各时长与类别准确率，质量范围由参考运行校准
- 检查失败/缺失视频单独记录，不将未处理视频排除出分母
- 检查首尾覆盖、帧去重、尺寸和 processor 后 token 实际计数；预算超限必须保留显式失败，不能静默删样本或截断后算通过。

## 应拒绝的失败方式

- 只凭字幕或题目作答而未执行视觉输入
- 循环少量帧冒充一小时视频
- 把标注答案或此前输出放入模型上下文

## 规模配方

### Debug：仅调通

- **data**：覆盖 short/medium/long 的 6 个真实视频
- **model**：72B 正式路径；7B 冒烟只能标为 debug-only
- **hardware_target**：T3：4×80 GiB GPU

### Reference large：正式生产规模

- **data**：全 900 视频与 2,700 题，包含真实 30–60 分钟视频；每个问题执行一次
- **model**：Qwen2.5-VL-72B-Instruct，BF16；subtitle-free；全时间轴含首尾均匀 max128frames、每帧≤448×448、视觉tokens≤32768、总输入≤40960、生成≤512；max_position_embeddings=65536 的长视频配置按模型卡建议在参考画像前验证锁定。
- **hardware_target**：T3：4×80 GiB GPU，NCCL/tensor-parallel 能力与足够媒体存储
- **useful_output**：完整视频内容问答目录

### 可选扩展：同一任务的变体

- **data**：原有视频分片；不复制、延长或循环媒体
- **hardware_target**：T3：最多 8 GPU，模型并行组或多个服务副本
- **not_new_task**：True

## GPU工作与预期资源形态

72B 权重、多个视频帧的视觉编码、长多模态上下文和数据搬运都是真实工作；完整媒体集合提供持续处理。

## 资源标签（待画像验证）

- large_weight_residency
- video_decode_pipeline
- multimodal_prefill
- h2d_stream
- multi_gpu_communication

## 设备能力

- CUDA
- BF16
- multi_gpu_tensor_parallel
- video_decode

## 后端要求

- 被测 sandbox 能访问声明的 GPU 设备与匹配的 CUDA/driver 用户态库；正式运行不静默转 CPU 或远程模型 API。
- 初始模型和输入在声明的只读路径，产物写入本 session 工作区；驱动兼容性与单/多 GPU 能力准入独立于功能验收。
- 多 GPU 间通信必须可用；视频解码所在 CPU/GPU 路径固定。

## 回放约束

- 替换的仅是负责决策的 agent LLM；本任务载入的模型及其 prefill、decode、embedding 或 reranking 每次都真实执行，不返回旧预测冒充执行。
- 冻结模型/数据内容哈希、tokenizer/processor、dtype、算子后端、解码及分片参数；服务端口和作业 ID 在本轮绑定，不能复用旧句柄。
- 工具完成以 CUDA 工作与输出提交完成为准；记录的模型等待不替代服务 ready、CUDA event 或文件落盘依赖。
- 上述预算是待参考验证的固定派生协议，不是 Video-MME 原生性能配置；所有后端用同一帧/时间与 processor 规则。

## Builder需要实现的部分

- 按来源条款取得媒体，冻结完整媒体清单与抽帧协议
- 验证指定模型/推理框架对 72B 视频输入和并行方式的支持
- 将官方答案评分与视频时间轴覆盖检查接入 oracle
- 实现上述派生视频预算与 64k long-video 配置；预先验证 decoder/processor 不再执行第二套隐式重采样或超限截断。

## 与相关任务的边界

视频语义问答；不同于 B 组动作识别训练或 C 组视频生成。

## 数据血缘

- video_mme

## 任务范围与条件

- 媒体仅学术研究，禁止在本包再分发；缺失视频必须更新实例版本并重新冻结清单。
- 254 小时是源媒体总时长，不是已测得 GPU 运行时间。
- 本任务采用声明的派生输入协议，不宣称复现官方排行榜精确配置。

## 来源记录

- [D_VIDEO_MME] Video-MME official dataset and evaluation — [来源](https://github.com/MME-Benchmarks/Video-MME)；检查位置：Overview; Dataset; Evaluation Pipeline; output_test_template.json and eval_your_results.py
- [D_QWENVL72] Qwen2.5-VL-72B-Instruct model card — [来源](https://huggingface.co/Qwen/Qwen2.5-VL-72B-Instruct)；检查位置：Local image/video inference and processing controls; model license; Processing Long Texts: long-video max_position_embeddings may be raised to 64k; YaRN caution

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
