# GPUv1-B07 · 训练点云语义分类并交付完整扫描标签

Train LiDAR semantic segmentation

**组别**：视觉理解、分割与三维感知　 **实施优先级**：advanced　 **阶段**：design

**Canonical goal**：`semantickitti_cylinder3d_labels`

**Workflow family**：`lidar_semantic_segmentation`

## 任务目标

为 SemanticKITTI 的完整扫描训练点级语义分割器，对验证序列每个点生成与原始扫描顺序对应的标签文件，并交付按距离统计的语义覆盖报告。

## 具体来源工作负载

Cylinder3D official config/semantickitti.yaml and train.sh; SemanticKITTI single-scan semantic segmentation; official semantic-kitti-api evaluator.

## 输入与配置

- dataset: SemanticKITTI / KITTI Odometry；split: 官方 train 序列 00–07、09、10；validation 08；assets: velodyne .bin、label .label、label mapping
- model: Cylinder3D single-scan；config: config/semantickitti.yaml; train.sh

## 需要完成的工作

- 按官方 learning_map 训练，同时保留逆映射。
- 执行源训练配置声明的完整计划，保存最佳与最终 checkpoint。
- 对完整序列 08 推理，输出每个原始点的标签和距离分层报告。

## 交付物

- Cylinder3D checkpoint 与有效配置
- sequences/08/predictions/*.label
- 逐类与按距离 IoU 报告
- label 映射与批量预测入口

## 后续使用与状态

从保存模型继续处理声明的未标注序列，生成结构正确的标签包；已处理扫描的标签和索引必须保持可追溯。

## 独立验收

- 核对每文件标签数等于原扫描点数，检查标签合法性与序列顺序。
- 应用官方逆映射后重算 mIoU 和距离分层指标，容差经参考校准。
- 不只依赖上游 submission 格式检查：额外拒绝全 ignored 或非法标签；抽样真实推理。

## 应拒绝的失败方式

- 输出体素标签但未映射回原始点
- 原始 ID 与训练 ID 混淆
- 用 ignored 类逃避误差
- 重复扫描或丢弃远处点

## 规模配方

### Debug：仅调通

- **data**：源序列中固定少量完整扫描
- **schedule**：仅验证稀疏算子、标签映射与输出对齐

### Reference large：正式生产规模

- **data**：完整官方 train 扫描及完整序列 08
- **model_config**：源 single-scan Cylinder3D 配置；构建时解析并冻结完整源训练计划
- **hardware_target**：T2：单张 80 GiB GPU，或 T3 2–4 GPU 经校准适配；未实测
- **useful_output**：可用分割模型和完整点级标签

### 可选扩展：同一任务的变体

- **data**：正式 test 序列 11–21 做额外批量推理，标签不用于本地精度判定
- **hardware_target**：按完整扫描分配 GPU；不拼接重复点增加规模
- **not_new_task**：True

## GPU工作与预期资源形态

完整扫描的非规则空间结构和稀疏三维卷积提供不同内存访问形态，点级输出还保留真实数据搬运。

## 资源标签（待画像验证）

- sparse_convolution
- pointwise_prediction
- variable_point_counts
- label_output

## 设备能力

- cuda
- spconv
- torch_scatter

## 后端要求

- 与源 spconv/torch-scatter 匹配的 CUDA 环境
- SemanticKITTI 数据及官方 label map
- 足够点云预处理内存

## 回放约束

- 保持点顺序和文件 ID 固定；不能把已有 label 作为模型返回。
- 若迁移旧 CUDA 依赖，必须重新建立参考画像与数值容差。

## Builder需要实现的部分

- 解析源训练配置并锁定依赖版本
- 封装逐点完整性与真实 IoU oracle
- 验证单/多 GPU 可执行配置并采集资源

## 与相关任务的边界

目标是每点语义和距离分层覆盖，不包含 B06 的对象框、朝向或速度回归。

## 数据血缘

- semantic_kitti

## 任务范围与条件

- 源 README 所列依赖较旧，环境移植是明确的 builder 工作。
- 源声称的多扫描/其他任务不自动视为当前代码已支持，本卡只采用 single-scan。

## 来源记录

- [B_CYLINDER3D] Cylinder3D official implementation — [来源](https://github.com/xinge008/Cylinder3D)；检查位置：SemanticKITTI preparation; config/semantickitti.yaml; train.sh; demo_folder.py
- [B_SEMANTICKITTI_API] SemanticKITTI evaluation API — [来源](https://github.com/PRBonn/semantic-kitti-api)；检查位置：Label mapping; evaluation; submission validation

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
