# GPUv1-C10 · 从单张参考图制作可渲染的 PBR 三维资产

Create renderable PBR 3D assets from reference images

**组别**：图像、视频、音频与三维生成　 **实施优先级**：standard　 **阶段**：design

**Canonical goal**：`hunyuan3d21_gso_pbr_asset_catalog`

**Workflow family**：`single_image_to_textured_3d`

## 任务目标

根据物体参考图批量制作带材质的三维资产，要求文件可重新载入、材质和纹理有效，并能在指定视角与灯光下渲染，交付可供三维场景使用的资产目录。

## 具体来源工作负载

Tencent Hunyuan3D-2.1 shape + paint pipeline / Google Scanned Objects 1,030-object collection

## 输入与配置

- GSO 全部 1,030 个物体的固定单视角渲染图；构建阶段从原始模型渲染，任务目录不提供原 mesh
- tencent/Hunyuan3D-2.1 的 shape 与 paint 权重及官方 rasterizer 依赖
- 冻结的坐标、相机、背景、mesh 导出和纹理协议；另有隐藏新视角参考

## 需要完成的工作

- 从输入图生成真实几何，再执行纹理/PBR 管线
- 保存独立 mesh/材质资产并重新载入
- 按请求相机和灯光渲染检查图，建立物体 ID 到资产的目录

## 交付物

- assets/<object_id>/scene.glb 或等价完整 mesh/material 包
- renders/<object_id>/
- asset-catalog.jsonl
- camera-and-generation-config.json

## 后续使用与状态

把指定已交付物体组成一个小场景，在新的相机/光照设置下渲染；必须复用实际生成几何和材质，不使用二维贴片替代。

## 独立验收

- 独立解析 mesh、拓扑索引、纹理引用和有限数值，确认全部资产可载入
- 在隐藏视角重新渲染，检查轮廓/视觉一致性；容差依据参考生成结果校准
- 检查新光照渲染响应与材质文件一致，无法用单张输入图通过
- 验证后续组合场景引用本轮生成资产

## 应拒绝的失败方式

- 返回输入图或一张带透明通道的 billboard
- 从 GSO 原始 mesh 直接复制答案
- 只输出未绑定材质的空几何或预览 PNG
- 报告形状成功但纹理阶段未完成

## 规模配方

### Debug：仅调通

- **workload**：GSO 中按 object ID 固定的 2 个真实物体
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：全部 1,030 个 GSO 物体，各一张固定真实渲染视图；逐物体执行官方形状与纹理生成，paint max_num_view=6/resolution=512 起点，保存完整资产
- **hardware_target**：T1：单张 48 GiB GPU；官方组合管线示例约 29 GB，具体 peak 待本环境实测
- **useful_output**：1,030 项可渲染的三维资产目录及重载验证图
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：不同物体按 ID 分片至多 GPU；更高纹理或网格精度仅作为同任务 scale，不作为新任务
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

3.3B 形状与 2B 纹理模型、多视图栅格化、纹理合成和 mesh 处理形成计算/显存/主机状态交替的真实三维工作流。

## 资源标签（待画像验证）

- multi_stage_gpu_pipeline
- large_resident_model
- custom_cuda_extension
- mesh_texture_state
- artifact_growth

## 设备能力

- CUDA
- BF16_or_FP16
- custom_rasterizer

## 后端要求

- 编译并固定官方 rasterizer/renderer CUDA 扩展
- 按许可证预置所有依赖权重
- 参考图构建和隐藏真值与实测工具执行分开

## 回放约束

- 形状、纹理和后续场景渲染都真实执行
- 逐阶段等待 GPU 完成，不能把异步生成返回当作完整资产
- 应用级 GLB 保存可移植，不假设 GPU 上下文可被任意 VMM 快照恢复

## Builder需要实现的部分

- 构建 GSO 单视图条件集并冻结所有相机及 object IDs
- 隐藏原始 mesh，制作新视角与材质验证
- 实现真实资产重载、批处理与按项失败记录

## 与相关任务的边界

交付三维几何和可重新照明的材质，验证必须重新渲染；与二维图像和视频生成任务具有不同产物与状态语义。

## 数据血缘

- google_scanned_objects
- hunyuan3d21

## 任务范围与条件

- GSO 转单视图的输入协议是本 benchmark 新构造，不声称官方 Hunyuan3D 评测恰好使用此集
- 大模型权重及 CUDA 扩展使后端能力要求高于纯 CPU sandbox

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_HUNYUAN3D] Hunyuan3D-2.1 — [来源](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)；检查位置：Model Zoo; Code Usage; shape generation and Hunyuan3DPaintConfig
- [C_GSO] Google Scanned Objects — [来源](https://research.google/blog/scanned-objects-by-google-research-a-dataset-of-3d-scanned-common-household-items/)；检查位置：Impact: 1,030 scanned objects; mesh/texture assets; linked Gazebo collection

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
