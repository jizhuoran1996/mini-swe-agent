# GPUv1-C04 · 从场景脚本生成完整视频素材库

Produce a video asset library from scene specifications

**组别**：图像、视频、音频与三维生成　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`wan22_a14b_vbench_video_assets`

**Workflow family**：`text_to_video_production`

## 任务目标

根据场景描述清单制作可播放的视频素材库，保证每个场景都有对应文件、参数记录和检索页；按场景目标保留动作、主体与时间结构。

## 具体来源工作负载

Wan2.2-T2V-A14B / generate.py --task t2v-A14B + VBench vbench/VBench_full_info.json

## 输入与配置

- Wan-AI/Wan2.2-T2V-A14B 和官方依赖权重
- VBench 标准 full_info 中按 prompt 文本去重的全部正式场景
- 固定 720p 输出、帧数、帧率、随机状态和采样设置

## 需要完成的工作

- 按场景 ID 建立制作清单，区分同一 prompt 的多个质量标签
- 真实生成视频并完整解码检查
- 组织视频、预览帧、参数和来源映射

## 交付物

- videos/<scene_id>.mp4
- shots.jsonl
- storyboard/index.html
- generation-config.json

## 后续使用与状态

使用已生成的指定镜头制作一个按冻结顺序排列的预览节目，保留原始镜头并交付时间线映射。

## 独立验收

- 逐视频校验完整帧数、分辨率和可解码性
- 利用 VBench 的适用维度和参考运行校准的容差检查主体/时间一致性
- 动作场景不能用静止图片循环代替；静态场景按照自身契约判断
- 核对所有镜头 ID 与文本对应，预览节目真实引用素材

## 应拒绝的失败方式

- 只提交公开视频样例
- 少量视频循环填满清单
- 任务声明生成尚未完成即返回成功
- 通过在线 Wan 服务替代本地推理

## 规模配方

### Debug：仅调通

- **workload**：固定 2 个源场景，使用同一 A14B 模型
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：VBench 标准去重场景全集；每场景一个 1280×720、81 帧视频，按官方模型配置固定帧率；不以多种子扩充任务数
- **hardware_target**：T2：单张 80 GiB GPU；先沿用官方单卡 offload 示例校准
- **useful_output**：完整场景视频库与预览节目
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：可采用官方 8 GPU FSDP + Ulysses 路径，需要 NCCL 和匹配互联；或独立分片，二者必须分别记录
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

大视频模型与时空注意力形成真实的高显存、长工具调用和大量解码/写回；不能用一个 toy clip 代替全集。

## 资源标签（待画像验证）

- large_resident_model
- sustained_gpu_compute
- long_tool_call
- video_latent_state
- optional_collective

## 设备能力

- CUDA
- BF16
- optional_NCCL

## 后端要求

- 固定 CUDA/PyTorch/attention 实现
- 为单卡 offload 配置足够宿主内存
- 多 GPU 路径声明 GPU 可见性和 collective 支持

## 回放约束

- 禁用运行时在线 prompt 扩写；所需文本在输入中冻结
- 仅替代 agent 的 LLM；视频模型及其编码器仍真实执行
- 等待 CUDA 与视频封装完成后才能产生工具成功事件

## Builder需要实现的部分

- 将 VBench 各维度重叠 prompt 去重并冻结 scene IDs
- 适配 Wan 批量制作与逐项结果存储
- 固定质量校验器的模型和输入范围

## 与相关任务的边界

从文本定义全新视频；C05 必须保持给定图像内容，C06 必须恢复已有视频未损坏的信息。

## 数据血缘

- vbench_t2v
- wan22_t2v_a14b

## 任务范围与条件

- 是 VBench 数据派生制作任务，不直接复现其多样本 leaderboard 协议
- 正式全集可能耗时很长；timeout 必须由参考画像确定而非随意裁掉尾部

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_WAN22] Wan2.2 — [来源](https://github.com/Wan-Video/Wan2.2)；检查位置：Run Text-to-Video Generation: t2v-A14B 1280*720; single-GPU and FSDP/Ulysses paths
- [C_VBENCH_T2V] VBench standard prompt and evaluation suite — [来源](https://github.com/Vchitect/VBench)；检查位置：Usage; vbench/VBench_full_info.json; sixteen T2V dimensions

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
