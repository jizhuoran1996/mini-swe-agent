# GPUv1-C01 · 批量生成可检索的高分辨率图像素材库

Build a high-resolution image asset library

**组别**：图像、视频、音频与三维生成　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`sdxl_coco2014_asset_catalog`

**Workflow family**：`text_to_image_asset_generation`

## 任务目标

根据给定描述清单生成完整的高分辨率图像素材库。每条描述必须对应真实生成图片、可追溯参数和可打开的浏览索引；交付后支持按素材编号重新导出指定子集。

## 具体来源工作负载

MLPerf Inference text_to_image / Stable Diffusion XL 1.0 / 官方 COCO 2014 5,000-sample 输入配置

## 输入与配置

- SDXL 1.0 官方权重和所需文本编码器、VAE
- MLPerf 所用 COCO 2014 captions/latent 输入清单，固定 5,000 个样本 ID
- 冻结的精度、scheduler、采样步数、尺寸和随机状态

## 需要完成的工作

- 从源输入建立 ID 到描述的映射并检查缺项
- 在 GPU 上实际执行所有指定图像生成，逐项保存结果
- 构建包含尺寸、来源和参数的 JSONL 清单及可浏览索引

## 交付物

- images/<sample_id>.png
- assets.jsonl
- contact-sheets/ 与 index.html
- generation-config.json

## 后续使用与状态

从已交付素材库中选出冻结清单指定的类别，生成新的展示目录和缩略图；保留原图和生成记录以便验证复用。

## 独立验收

- 检查全部输入 ID 恰好对应一张可解码图片，尺寸与冻结协议一致
- 独立重算约定的 CLIP/FID 类质量统计，阈值依据本任务参考运行校准，不照抄公开榜单值
- 对固定小样本重新执行并用预先校准的感知容差检查生成路径；检查索引确实引用实际文件

## 应拒绝的失败方式

- 只输出 MLPerf 日志或分数而没有图片
- 复制 COCO 原图充当生成结果
- 缺失项用同一张图反复填充
- 测量期间改用远程生成 API

## 规模配方

### Debug：仅调通

- **workload**：同一清单的固定 8 个真实描述
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：官方 5,000 个 COCO 2014 样本，各生成一张 1024×1024 图；完整推理配置冻结
- **hardware_target**：T1：单张 24–48 GiB CUDA GPU；工程目标，非本包实测
- **useful_output**：5,000 张图片及其资产目录
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：将同一 5,000 项按 ID 分片到 2–8 张独立 GPU，无需跨卡 collective；保持总有效素材数不变
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

持续扩散推理、文本编码和 VAE 解码带来实际 GPU 工作，图像落盘形成输出状态；模型驻留可跨后续操作保留。

## 资源标签（待画像验证）

- sustained_gpu_compute
- resident_model
- gpu_to_host_transfer
- artifact_growth

## 设备能力

- CUDA
- FP16_or_BF16

## 后端要求

- GPU 设备和匹配的宿主驱动可见
- 权重预置与下载阶段单独计时
- 有足够本地输出空间

## 回放约束

- 替代的是决策 LLM；SDXL 与文本编码器仍真实执行
- 固定描述、初始 latent 和参数；完成事件在 GPU 结果可消费后记录
- 源 LoadGen 的重复查询不能冒充新的素材或新的独立任务

## Builder需要实现的部分

- 编写将 reference pipeline 结果保存为资产库的薄适配器
- 冻结源样本清单及模型内容 hash
- 实现图像清单和独立质量校验

## 与相关任务的边界

目标是从文本交付新图像库；C02 修复局部缺失，C03 保持已有场景结构，二者输入约束不同。

## 数据血缘

- coco2014
- mlperf_inference_sdxl

## 任务范围与条件

- 是 MLPerf 工作负载派生任务，不宣称一次 agent 运行满足官方 MLPerf 提交规则
- 生成质量存在随机数与算子实现相关差异，需要固定并校准容差

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_MLPERF_SDXL] MLPerf Inference SDXL workload and SCC24 guide — [来源](https://docs.mlcommons.org/inference/benchmarks/text_to_image/reproducibility/scc24/)；检查位置：Introduction: SDXL 1.0, COCO 2014 and 5,000-sample workload; source-linked reference implementation

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
