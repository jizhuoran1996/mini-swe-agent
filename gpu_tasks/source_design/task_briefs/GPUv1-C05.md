# GPUv1-C05 · 将静态素材制作成保持主体的动态镜头

Animate reference images while preserving subject identity

**组别**：图像、视频、音频与三维生成　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`hunyuan_i2v_vbench_reference_animation`

**Workflow family**：`image_to_video_animation`

## 任务目标

把给定静态图像制作成动态镜头，遵守对应运动说明并保持参考主体和场景。交付镜头、输入映射与对照审阅页，用于基于静态素材的视频制作。

## 具体来源工作负载

Tencent-Hunyuan/HunyuanVideo-I2V / sample_image2video.py + VBench-I2V vbench2_i2v_full_info.json

## 输入与配置

- VBench-I2V 官方 Image Suite 与 vbench2_i2v_full_info.json 中匹配条目
- 官方 HunyuanVideo-I2V 修正版本的权重和依赖编码器，构建时固定 hash
- 每个不同 image_name 的基准请求及源 camera_motion 请求；不添加随机复制请求

## 需要完成的工作

- 校验图片及其 prompt/运动标签
- 按固定 720p 管线生成完整片段并保留对应参考图
- 导出首帧和跨时间采样对照及文件清单

## 交付物

- clips/<request_id>.mp4
- reference-map.jsonl
- review-contact-sheets/

## 后续使用与状态

按要求把已完成镜头归组为展示序列，并针对清单中的额外原生 camera_motion 请求继续制作；全部请求在采集前冻结。

## 独立验收

- 逐请求检查图片、视频和运动条件映射完整
- 检测首帧/主体保持、时间一致性与原生运动标签；以参考运行校准范围
- 完整解码确认帧数和分辨率，禁止静图重复冒充有运动的请求
- 对照页必须关联实际视频与原始参考图片

## 应拒绝的失败方式

- 将所有请求变成纯文本视频生成
- 省略图像条件或首帧引用了别的样本
- 下载模型演示视频作为输出
- 为降低显存偷偷删减帧数

## 规模配方

### Debug：仅调通

- **workload**：2 个不同 reference images 及其基准请求
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：官方 I2V full_info 中全部去重的 image/prompt 对；每项 720p、129 帧，精度及 scheduler 用固定官方配置
- **hardware_target**：T2：单张 80 GiB GPU；官方 720p 表给出约 60 GB 峰值，仍需本环境实测
- **useful_output**：完整的参考图像动画库
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：官方 xDiT sequence-parallel 路径可作为 2–8 GPU 配置，需 NCCL；不得把卡数当新任务
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

图像条件、多模态文本编码、时空 token 注意力与视频解码形成大模型驻留及长执行区间。

## 资源标签（待画像验证）

- large_resident_model
- image_conditioning
- video_latent_state
- host_device_transfer

## 设备能力

- CUDA
- BF16
- optional_NCCL

## 后端要求

- 固定匹配的 FlashAttention / xDiT 版本
- 输入图片解码和缩放规则写入 manifest
- 按授权获得并预置 Image Suite

## 回放约束

- prompt 扩写若需要只在构建或采集阶段固定
- 工具返回时视频必须完整落盘；不把异步任务提交当生成完成
- 静态图、模型和输出状态可跨轮保留，是否保留按真实操作记录

## Builder需要实现的部分

- 冻结官方图像和元数据一一映射
- 检查各长宽比到 720p 的确定性变换
- 实现图像保持与镜头可播放性的独立验证

## 与相关任务的边界

条件图像与主体保持是主要交付约束，不是为 C04 换模型或增加一个 prompt。

## 数据血缘

- vbench_i2v
- hunyuanvideo_i2v

## 任务范围与条件

- 源数据中同一图像可有多个原生运动请求，采样需保留同源关系
- 不能把原始相同素材的多个运动版本当独立任务家族

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_HUNYUAN_I2V] HunyuanVideo-I2V — [来源](https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V)；检查位置：Requirements; sample_image2video.py; first-frame consistency; xDiT parallel inference
- [C_VBENCH_I2V] VBench-I2V image/prompt bindings — [来源](https://github.com/Vchitect/VBench/blob/master/vbench2_beta_i2v/vbench2_i2v_full_info.json)；检查位置：image_name, prompt_en, dimension and image_type records

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
