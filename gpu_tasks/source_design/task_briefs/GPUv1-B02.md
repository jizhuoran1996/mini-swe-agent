# GPUv1-B02 · 为开放图像库建立可查询的目标框目录

Build an object catalogue for OpenImages

**组别**：视觉理解、分割与三维感知　 **实施优先级**：pilot　 **阶段**：design

**Canonical goal**：`openimages_v6_object_catalogue`

**Workflow family**：`image_object_cataloguing`

## 任务目标

把 OpenImages V6 的完整验证图像库转为可查询的目标框目录。每条对象记录包含原始 image ID、600 类映射中的类别、置信度和原图坐标框；交付按类别检索图片及按图片列出对象的查询入口。

## 具体来源工作负载

MMDetection OpenImages V6 RetinaNet R50-FPN: configs/openimages/retinanet_r50_fpn_32xb2-1x_openimages.py and matching published checkpoint.

## 输入与配置

- dataset: OpenImages V6；split: 完整 validation；annotations: bbox、image-level labels、600 类 hierarchy；标签只向独立 oracle 提供
- model_config: retinanet_r50_fpn_32xb2-1x_openimages.py；weights: OpenMMLab 该配置匹配的发布 checkpoint

## 需要完成的工作

- 核对完整图像清单和模型的类别层级映射。
- 在 GPU 上对每幅真实图像执行检测，恢复原图坐标，记录无检测结果的图片。
- 保存框目录并实现类别和图片查询；输出覆盖率与实际验证指标。

## 交付物

- detections.parquet 与图片覆盖清单
- class_hierarchy.json
- query_catalog.py
- 冻结的推理配置及验证报告

## 后续使用与状态

对指定类别查询目录，交付所有匹配图像及框裁剪索引；接收一批预先声明的新增源图片后追加检测，不覆盖原有记录。

## 独立验收

- 独立枚举输入，检查每图覆盖、坐标边界、合法类别、数值有限性与目录查询一致性。
- 按 OpenImages 的 image-level label 与层级规则重算实际 box AP；与固定参考输出比较，容差经校准。
- 抽取冻结图像重跑模型，检测复制框、错序或伪造目录。

## 应拒绝的失败方式

- 交付公开榜单分数而无逐图检测结果
- 把训练/验证 bbox 当模型预测
- 遗漏没有检测框的图片
- 新增索引污染旧图记录

## 规模配方

### Debug：仅调通

- **data**：固定 128 张有不同尺寸/目标数量的真实 validation 图
- **use**：结构、类别映射和 GPU 通路调试

### Reference large：正式生产规模

- **data**：完整 OpenImages V6 validation 检测图像清单；不以几百张 calibration 子集代替
- **model_config**：600 类 RetinaNet R50-FPN 发布配置和 checkpoint，保留声明分辨率/阈值
- **hardware_target**：T1：单张 24–48 GiB GPU；GPU 常驻推理与完整批量输出，未实测
- **useful_output**：完整可查询目标框目录

### 可选扩展：同一任务的变体

- **data**：可扩至 V6 public test 图像清单；固定同一预测和目录契约
- **hardware_target**：2–4 GPU 按 image ID 分片；没有虚构重复请求
- **not_new_task**：True

## GPU工作与预期资源形态

完整图像库的密集检测产生持续特征金字塔计算、变化尺寸输入和结果回传，同时可保留模型处理后续批次。

## 资源标签（待画像验证）

- bulk_inference
- variable_image_shapes
- model_residency
- h2d_d2h
- artifact_index

## 设备能力

- cuda
- fp32
- optional_amp

## 后端要求

- MMDetection/MMCV CUDA 运算兼容
- 足够主机图片缓存与可写目录
- 独立 oracle 能读私有标签

## 回放约束

- 数据目录生成时真跑检测；不能回放既有检测结果替代 GPU 工作。
- 固定 NMS、尺寸变换和原图坐标还原；模型 worker 句柄用本轮绑定。

## Builder需要实现的部分

- 锁定 checkpoint、图片 bytes 和类别表
- 实现目录查询/追加逻辑与 oracle
- 确认实际推理达到正式 GPU 工作量准入

## 与相关任务的边界

交付多类别物体位置和查询目录，属于批量视觉数据生产；与 B01 分类训练和 B03 像素轮廓训练分别计 lineage。

## 数据血缘

- openimages_v6

## 任务范围与条件

- 这是来源派生的应用任务，不声称 MLPerf 合规结果。
- 模型规模适中，但正式集使用完整真实图像清单；显存强度由参考画像判定。

## 来源记录

- [B_OPENIMAGES] MMDetection OpenImages recipes — [来源](https://github.com/open-mmlab/mmdetection/blob/main/configs/openimages/README.md)；检查位置：Open Images v6 data preparation; model table; image-level label evaluation notes
- [B_RETINANET_CONFIG] OpenImages RetinaNet R50-FPN config — [来源](https://github.com/open-mmlab/mmdetection/blob/main/configs/openimages/retinanet_r50_fpn_32xb2-1x_openimages.py)；检查位置：retinanet_r50_fpn_32xb2-1x_openimages.py

资源额度为工程规划；实际GPU/主机用量与运行时间记录在`reference_measurements`，当前未测字段为null。实例分片与后续阶段遵守`INSTANCE_AND_ORACLE.md`，资源准入遵守`GPU_ADMISSION.md`。
