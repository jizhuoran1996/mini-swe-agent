# GPUv1-C03 · 保持场景布局的图像风格转换

Transform image appearance while retaining scene layout

**组别**：图像、视频、音频与三维生成　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`flux_canny_coco2017_layout_preserving_catalog`

**Workflow family**：`structure_conditioned_image_transformation`

## 任务目标

将指定照片集转换成统一的插画素材集，同时保留主体布局和主要轮廓。输出应包含新图像、使用的边缘条件以及原图与生成图的映射，供后续排版使用。

## 具体来源工作负载

FLUX.1-Canny-dev / FluxControlPipeline + COCO 2017 val images 与 captions

## 输入与配置

- COCO 2017 validation 全部图像和 captions；每图按 annotation ID 固定选一条描述
- black-forest-labs/FLUX.1-Canny-dev
- 冻结的插画风格 brief、Canny 阈值与尺寸转换策略

## 需要完成的工作

- 提取并保存每张输入的 Canny 结构条件
- 把图像描述与固定风格 brief 组合为可追溯输入
- 执行结构条件扩散并构建原图/边缘/新图对照目录

## 交付物

- transformed/<image_id>.png
- controls/<image_id>.png
- layout-catalog.jsonl
- comparison-gallery/

## 后续使用与状态

从已经生成的集合中制作指定版面的图册，保持 ID 及原图归属，并能追溯每张图的条件输入。

## 独立验收

- 核对所有 5,000 张验证图的输出覆盖和数据关联
- 重算边缘/布局一致性与风格/语义质量检查；容差由参考产物确定
- 拒绝输入图片原样输出或条件图被当作最终成品
- 核对后续排版实际读取生成素材

## 应拒绝的失败方式

- 无视 control image 只调用普通文本生成
- 把单一边缘图重复用于全部输入
- 直接交付照片或二值边缘图
- 通过降低输出分辨率而违反交付条件

## 规模配方

### Debug：仅调通

- **workload**：固定 8 张验证图片，保持正式图像变换规则
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：COCO val2017 全部 5,000 张独立照片；长边按目标 1024 像素且保持比例，固定单一风格与采样协议
- **hardware_target**：T2：单张 80 GiB GPU；工程目标，非已测最低配置
- **useful_output**：完整布局一致的插画素材库和结构条件库
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：不同图像按 ID 分片；多卡不改变每张图的生成语义
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

结构提取、条件变换器、文本编码器及图像解码形成不同于无条件图像库的设备计算和数据搬运。

## 资源标签（待画像验证）

- large_resident_model
- preprocess_gpu_pipeline
- conditional_generation
- artifact_growth

## 设备能力

- CUDA
- BF16

## 后端要求

- 安装与固定 controlnet_aux / diffusers 兼容版本
- 保持颜色空间、长宽比处理和边缘参数一致

## 回放约束

- 固定风格 brief 不调用在线 prompt expansion
- 真实执行任务侧编码与扩散；已采集的 agent 文本仅控制操作
- 数据转换缓存是否保留属于实验配置

## Builder需要实现的部分

- 构造 COCO ID/caption/edge 三方映射
- 固定明确的风格 brief 并做参考质量校准
- 实现保持轮廓而允许外观变化的验收

## 与相关任务的边界

该任务要求全图外观转换并保持已有布局，不是 C02 的局部内容填补，也不是 C01 的自由生成。

## 数据血缘

- coco2017
- flux1_canny

## 任务范围与条件

- 与 C02 同属 FLUX 家族，报告软件家族关联
- 风格相似度与边缘相似度仅用于已固定任务验证，不作为 sandbox 性能综合分

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_FLUX_CANNY] FLUX.1 Canny [dev] — [来源](https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev)；检查位置：Diffusers FluxControlPipeline with CannyDetector
- [C_COCO] COCO dataset and downloads — [来源](https://cocodataset.org/#download)；检查位置：COCO image-caption dataset; 2017 validation input specification

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
