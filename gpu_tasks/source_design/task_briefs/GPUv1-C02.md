# GPUv1-C02 · 完成带掩码图片并保留未编辑区域

Complete masked images while preserving visible content

**组别**：图像、视频、音频与三维生成　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`flux_fill_brushbench_inside_completion`

**Workflow family**：`masked_image_completion`

## 任务目标

补全素材目录中被掩码标记、已经真正移除的图像区域，按照对应源描述生成合理内容，保持未遮挡区域，并交付可逐图对照的完成项目。

## 具体来源工作负载

FLUX.1-Fill-dev + BrushBench 官方 mapping_file.json / inpainting_mask（inside-mask 条目；受损输入由 builder 从源图按掩码派生）

## 输入与配置

- BrushBench 官方 mapping_file.json 中 inside-mask 条目的受损图片、inpainting_mask 和对应源 caption；builder 在交付前已将 mask 内像素删除或替换为固定中性色
- 任务环境不含干净原图、可恢复原图的缓存、原数据包或下载地址；干净原图仅在独立 oracle 存储中可见
- black-forest-labs/FLUX.1-Fill-dev 权重与依赖编码器
- 每图固定的目标尺寸、掩码方向和像素清除规则；正式配置保留可见区域原始细节且不人为上采样凑规模

## 需要完成的工作

- 读取并校验受损图像、掩码和描述的一一对应；只使用仍可见的上下文
- 真实执行 FluxFillPipeline；将生成区域与受损输入中的未编辑区域合成保存
- 导出受损输入、掩码和最终图片的对照索引

## 交付物

- completed/<id>.png
- mask-and-transform-manifest.jsonl
- review/index.html

## 后续使用与状态

将已完成项目按给定交付分组重新导出；对采集前冻结的额外 inside-mask 请求，builder 同样只提供真正清除区域后的受损图，后续处理不能取得 oracle 中的干净原图。

## 独立验收

- 解码所有结果并核对完整 inside-mask 输入覆盖；验证运行独立读取干净参考，不将它复制或挂载至任务目录
- 未编辑像素在约定颜色转换后与受损输入的可见区域一致；禁止反转掩码
- 对生成区域单独计算感知与源文本一致性统计，阈值依据参考运行校准；对语义可多解的条目不要求恢复唯一原始像素
- 检查输出不是受损图、固定中性色填充或重复图片；最终图片中的 mask 区域必须实际完成

## 应拒绝的失败方式

- 原样返回受损输入或固定颜色填充
- 泄露干净原图、其缓存或源压缩包到 agent 环境
- 全图重绘破坏需保持的可见内容
- 只保存缩略图

## 规模配方

### Debug：仅调通

- **workload**：完整列表中的固定 4 张不同场景图
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：BrushBench 全部正式 inside-mask 条目；逐图保留其自然分辨率或按已声明尺寸策略约束长边，50 步作为待固定的源示例起点
- **hardware_target**：T2：单张 80 GiB GPU；权重/编码器驻留与 offload 策略在画像前确定
- **useful_output**：完整的带局部编辑约束的图片交付项目
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：按不同图像分片到多 GPU；不能把换掩码、换种子或调步数统计为新 canonical task
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

12B 扩散变换器加图像编码、局部条件和解码提供大模型推理路径，单样本也具有实质模型驻留。

## 资源标签（待画像验证）

- large_resident_model
- conditional_generation
- image_state
- host_device_transfer

## 设备能力

- CUDA
- BF16

## 后端要求

- 模型授权后在构建阶段预置权重
- 冻结可用显存和 CPU offload 路径
- 保存受损输入、掩码和编辑项目；干净原图仅保存在独立 oracle 存储

## 回放约束

- Fill 推理必须本地真实执行，不返回已缓存的参考结果
- 后续请求引用逻辑图像 ID，不引用采集时随机临时路径
- 请求完成以最终图片可读为准

## Builder需要实现的部分

- 取得并冻结 BrushBench 官方 inside-mask 条目、对应源 caption 及授权输入清单
- 在构建阶段按 inpainting_mask 真正删除或中性色填充源图对应区域；统一处理 mask 边界和颜色空间，并保存受损输入哈希
- 将干净原图放入独立 oracle-only 存储；任务环境只打包受损图、mask、caption，禁止带入原始完整数据包、可逆清除信息或原图缓存
- 构建 FluxFill 输入适配，以及可见区域保持和生成区域质量的分离验证

## 与相关任务的边界

输入具有不可变上下文和指定缺失区域，目标不同于全文本生成及边缘控制的全图外观转换。

## 数据血缘

- brushbench
- flux1_fill

## 任务范围与条件

- 模型/数据存在授权下载条件，包不含这些资产
- 仅纳入源 inside-mask 语义的补全请求；不把任意指令编辑条目都当作原图重建
- 生成区域存在合理多解，原始干净图仅作为隐藏参考之一，不做逐像素强制匹配

## 输入可见范围

- **agent_visible**：corrupted_image；inpainting_mask；source_caption；frozen_transform_config
- **oracle_only**：clean_source_image；full_original_dataset_archive
- **corruption**：mask 内像素在构建阶段真正移除或固定中性色填充，不能通过 alpha 通道、额外图层或缓存恢复

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_FLUX_FILL] FLUX.1 Fill [dev] — [来源](https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev)；检查位置：Model description and FluxFillPipeline image/mask inference example
- [C_BRUSHBENCH] BrushNet / BrushBench — [来源](https://github.com/TencentARC/BrushNet)；检查位置：Data Download; data/BrushBench/mapping_file.json; Evaluation --mask_key inpainting_mask

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
