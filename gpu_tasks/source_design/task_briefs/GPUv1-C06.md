# GPUv1-C06 · 恢复高分辨率视频的缺失区域

Restore missing regions in high-resolution videos

**组别**：图像、视频、音频与三维生成　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`propainter_davis_fullresolution_completion`

**Workflow family**：`temporal_video_restoration`

## 任务目标

修复一组真实视频中由给定逐帧掩码标记的缺失区域，在保留其余画面的同时恢复连续内容，并交付完整恢复片段和逐帧对照。

## 具体来源工作负载

ProPainter Releases V0.1.0 / datasets/davis/test.json 与发布 test_masks + DAVIS 2017 Full-Resolution TrainVal

## 输入与配置

- DAVIS 2017 Full-Resolution TrainVal 中 ProPainter datasets/davis/test.json 指定的全部视频
- ProPainter 发布的 DAVIS test_masks；确定性映射至对应分辨率
- ProPainter.pth、recurrent_flow_completion.pth、raft-things.pth

## 需要完成的工作

- 将官方掩码与完整帧序列匹配，生成受损输入；干净真值由验证侧保留
- 在 GPU 上真实计算光流、传播与恢复，不仅运行视频拼接
- 导出全部恢复帧和按源时间轴编码的视频

## 交付物

- restored/<video_id>/frames/
- restored/<video_id>.mp4
- frame-map.jsonl
- restoration-config.json

## 后续使用与状态

按指定视频和时间段从恢复项目导出剪辑，保证访问已有恢复状态且不改变原序列帧顺序。

## 独立验收

- 验证输入/输出逐帧数量和时间映射
- 检查掩码外区域按约定编码容差保持一致
- 对隐藏干净帧计算恢复质量及时间一致性，阈值从固定参考执行校准
- 检查恢复帧不是原受损帧或跨视频复制品

## 应拒绝的失败方式

- 忽略掩码只重新编码视频
- 把原图全集泄露到任务目录再复制为输出
- 裁掉难恢复帧或缩短序列
- 用相同画面循环填满输出

## 规模配方

### Debug：仅调通

- **workload**：官方 test list 中固定 1 个完整短序列
- **purpose**：仅验证下载后输入、执行入口及输出契约，不作为正式大负载

### Reference large：正式生产规模

- **workload**：ProPainter 官方 DAVIS test list 全集、完整帧；使用 DAVIS full-resolution 源，长边上限 1280，禁止对低分辨率源人为放大；fp16、subvideo_length=80 作为固定起点
- **hardware_target**：T1：单张 48 GiB GPU；窗口/分辨率需先校准，非固定模型参数量代表其峰值
- **useful_output**：完整真实视频恢复项目
- **status**：proposed_unmeasured

### 可选扩展：同一任务的变体

- **workload**：按不同原生视频分配独立 GPU；更高源分辨率属于同任务规模扩展，不通过复制帧变长
- **counting**：同一任务的运行或规模配置，不产生新 task ID

## GPU工作与预期资源形态

光流与时序传播保留多个帧的中间状态；高分辨率自然视频可产生明显工作集和主机/设备帧搬运，即使权重比视频生成模型小。

## 资源标签（待画像验证）

- temporal_working_set
- gpu_memory_pressure
- frame_io
- host_device_transfer

## 设备能力

- CUDA
- FP16

## 后端要求

- 固定解码、mask 插值与颜色转换
- 匹配源许可证并提供完整本地视频
- 窗口配置不得由各后端静默改变

## 回放约束

- 完整原生序列是任务单位，窗口只影响执行实现
- 完成区间包括实际 GPU 处理和交付编码；验证开销单独标记
- 不能用 GPU context snapshot 假定替代跨轮状态保存

## Builder需要实现的部分

- 绑定并核对官方 test list 与 Full-Resolution 帧
- 实现 mask 到源尺寸的冻结适配
- 隐藏 clean reference 并实现独立 restoration oracle

## 与相关任务的边界

恢复已有视频中的缺失信息，要求保持已知内容和时间轴；与 C04/C05 的新视频合成有不同功能目标。

## 数据血缘

- davis2017
- propainter

## 任务范围与条件

- 正式分辨率与官方低分辨率榜单协议不同，必须标为派生设置
- 以源 test list 为准，不将 DAVIS 全部 90 条误报为官方 ProPainter test 集

## 验收范围

- **integrity**：全量 ID、文件、参数、形状、长度和交付关系检查
- **semantic_quality**：使用固定本地评价模型或隐藏参考；在相同原生数据协议下校准质量容差
- **accounting**：验证工作单独标注；主要生成必须发生在真实工具执行中，不由 grader 代做
- **external_llm_judge**：False

## 来源记录

- [C_PROPAINTER] ProPainter — [来源](https://github.com/sczhou/ProPainter)；检查位置：Pretrained Releases V0.1.0; Dataset preparation; datasets/davis/test.json; inference_propainter.py
- [C_DAVIS] DAVIS 2017 dataset — [来源](https://davischallenge.org/davis2017/code.html)；检查位置：TrainVal images; 480p and Full-Resolution downloads

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
